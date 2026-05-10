# scripts/retrain_from_feedback.py

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoImageProcessor, AutoModel


# =============================================================================
# CONFIG
# =============================================================================

MODEL_NAME = "facebook/dinov2-large"
EMBEDDING_MODE = "cls_mean"
EMBEDDING_DIM = 2048

FINAL_CONFIG_NAME = "top18_contemporary_feedback_retrain_v1"

MERGED_CLASS_NAME = "Contemporary_Art"

CLASS_GROUPING = {
    MERGED_CLASS_NAME: [
        "Minimalism",
        "Pop_Art",
        "Color_Field_Painting",
    ]
}

DISPLAY_NAMES = {
    "Contemporary_Art": "Современное искусство",
}

# Только safety fallback.
# В нормальном проме backend уже должен отдавать Contemporary_Art.
OLD_TO_MERGED_LABEL = {
    "Minimalism": "Contemporary_Art",
    "Pop_Art": "Contemporary_Art",
    "Color_Field_Painting": "Contemporary_Art",
}

FORBIDDEN_FINAL_LABELS = {
    "Minimalism",
    "Pop_Art",
    "Color_Field_Painting",
}


# =============================================================================
# UTILS
# =============================================================================

def atomic_copy(src: Path, dst: Path) -> None:
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def l2_normalize_vector(x: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    x = x.astype(np.float32)
    return x / (np.linalg.norm(x) + eps)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    return h.hexdigest()


def normalize_feedback_label(label: str) -> str:
    label = str(label).strip()
    return OLD_TO_MERGED_LABEL.get(label, label)


def resolve_image_path(image_path_raw: str, images_root: Path | None, csv_path: Path) -> Path:
    image_path = Path(str(image_path_raw).strip())

    if image_path.is_absolute():
        return image_path

    if images_root is not None:
        return images_root / image_path

    return csv_path.parent / image_path


def json_dump(path: Path, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# =============================================================================
# DINO EMBEDDER
# =============================================================================

class DinoEmbedder:
    def __init__(self, device: torch.device) -> None:
        self.device = device

        print(f"loading_encoder={MODEL_NAME}")

        self.processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
        self.encoder = AutoModel.from_pretrained(MODEL_NAME).to(device)

        self.encoder.eval()

        for p in self.encoder.parameters():
            p.requires_grad = False

    @torch.no_grad()
    def get_embedding(self, image: Image.Image) -> np.ndarray:
        inputs = self.processor(
            images=image.convert("RGB"),
            return_tensors="pt",
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        out = self.encoder(**inputs)
        hidden = out.last_hidden_state

        cls = hidden[:, 0]

        if EMBEDDING_MODE == "cls":
            emb = cls
        elif EMBEDDING_MODE == "cls_mean":
            patches = hidden[:, 1:].mean(dim=1)
            emb = torch.cat([cls, patches], dim=-1)
        else:
            raise ValueError(f"Unknown EMBEDDING_MODE={EMBEDDING_MODE}")

        emb_np = emb.squeeze(0).cpu().numpy().astype(np.float32)
        return l2_normalize_vector(emb_np)


# =============================================================================
# MODEL HEAD
# =============================================================================

class ResidualBlock(nn.Module):
    def __init__(self, dim: int, dropout: float = 0.2):
        super().__init__()

        self.block = nn.Sequential(
            nn.LayerNorm(dim),
            nn.Linear(dim, dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim, dim),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.block(x)


class ResidualStyleHead(nn.Module):
    def __init__(
        self,
        in_dim: int,
        num_classes: int,
        hidden_dim: int = 512,
        num_blocks: int = 3,
        dropout: float = 0.2,
    ):
        super().__init__()

        self.proj = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        self.blocks = nn.Sequential(
            *[ResidualBlock(hidden_dim, dropout) for _ in range(num_blocks)]
        )

        self.head = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.blocks(self.proj(x)))


def make_class_weights(
    y_train: np.ndarray,
    num_classes: int,
    mode: str = "inv_sqrt",
    max_weight: float = 5.0,
) -> torch.Tensor:
    counts = np.bincount(y_train, minlength=num_classes).astype(np.float32)
    counts = np.maximum(counts, 1.0)

    if mode == "inv_sqrt":
        w = 1.0 / np.sqrt(counts)
    elif mode == "inv":
        w = 1.0 / counts
    elif mode == "balanced":
        w = len(y_train) / (num_classes * counts)
    else:
        raise ValueError(f"Unknown class weight mode: {mode}")

    w = w / w.mean()
    w = np.minimum(w, max_weight)
    w = w / w.mean()

    return torch.tensor(w, dtype=torch.float32)


@torch.no_grad()
def predict_logits(
    model: nn.Module,
    X_eval: np.ndarray,
    device: torch.device,
    batch_size: int = 4096,
) -> torch.Tensor:
    model.eval()
    parts = []

    X_eval = X_eval.astype(np.float32)

    for start in range(0, len(X_eval), batch_size):
        xb = torch.tensor(
            X_eval[start:start + batch_size],
            dtype=torch.float32,
            device=device,
        )
        parts.append(model(xb).detach().cpu())

    return torch.cat(parts, dim=0)


def train_head(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    num_classes: int,
    device: torch.device,
    epochs: int,
    batch_size: int,
    lr: float,
    weight_decay: float,
    label_smoothing: float,
    class_weight_mode: str,
    patience: int,
    seed: int,
) -> tuple[nn.Module, float, np.ndarray, dict]:
    set_seed(seed)

    model = ResidualStyleHead(
        in_dim=EMBEDDING_DIM,
        num_classes=num_classes,
    ).to(device)

    class_weights = make_class_weights(
        y_train,
        num_classes=num_classes,
        mode=class_weight_mode,
    ).to(device)

    criterion = nn.CrossEntropyLoss(
        weight=class_weights,
        label_smoothing=label_smoothing,
    )

    loader = DataLoader(
        TensorDataset(
            torch.tensor(X_train, dtype=torch.float32),
            torch.tensor(y_train, dtype=torch.long),
        ),
        batch_size=batch_size,
        shuffle=True,
        pin_memory=(device.type == "cuda"),
        num_workers=0,
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=lr,
        weight_decay=weight_decay,
    )

    warmup = max(1, epochs // 10)

    def lr_lambda(ep: int) -> float:
        if ep < warmup:
            return (ep + 1) / warmup

        progress = min(1.0, (ep - warmup) / max(1, epochs - warmup))
        return 0.5 * (1.0 + np.cos(np.pi * progress))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    best_acc = -1.0
    best_weights = None
    best_epoch = -1
    bad_epochs = 0

    history = {
        "train_loss": [],
        "val_acc": [],
        "lr": [],
        "best_epoch": None,
    }

    for epoch in range(epochs):
        model.train()

        total_loss = 0.0
        n_seen = 0

        for xb, yb in loader:
            xb = xb.to(device, non_blocking=True)
            yb = yb.to(device, non_blocking=True)

            optimizer.zero_grad(set_to_none=True)

            loss = criterion(model(xb), yb)
            loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            total_loss += float(loss.item()) * len(xb)
            n_seen += len(xb)

        scheduler.step()

        train_loss = total_loss / max(1, n_seen)

        val_preds = predict_logits(model, X_val, device=device).argmax(1).numpy()
        val_acc = accuracy_score(y_val, val_preds)

        history["train_loss"].append(float(train_loss))
        history["val_acc"].append(float(val_acc))
        history["lr"].append(float(scheduler.get_last_lr()[0]))

        if val_acc > best_acc + 1e-5:
            best_acc = float(val_acc)
            best_weights = copy.deepcopy(model.state_dict())
            best_epoch = epoch + 1
            bad_epochs = 0
        else:
            bad_epochs += 1

        print(
            f"epoch={epoch + 1:03d}/{epochs} "
            f"loss={train_loss:.4f} "
            f"val_acc={val_acc:.4f} "
            f"best={best_acc:.4f}@{best_epoch}"
        )

        if bad_epochs >= patience:
            print(f"early_stopping best_epoch={best_epoch}")
            break

    if best_weights is None:
        raise RuntimeError("No best weights saved")

    model.load_state_dict(best_weights)
    model.eval()

    val_preds = predict_logits(model, X_val, device=device).argmax(1).numpy()
    history["best_epoch"] = best_epoch

    return model, best_acc, val_preds, history


# =============================================================================
# FEEDBACK READING / EMBEDDING
# =============================================================================

def read_feedback_csv(path: Path) -> list[dict]:
    rows = []

    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        required_cols = {"image_path", "correct_style_code"}
        missing = required_cols - set(reader.fieldnames or [])

        if missing:
            raise ValueError(f"Feedback CSV missing columns: {sorted(missing)}")

        for row in reader:
            rows.append(row)

    return rows


def build_feedback_features(
    feedback_rows: list[dict],
    known_classes: set[str],
    device: torch.device,
    feedback_csv_path: Path,
    images_root: Path | None,
) -> tuple[np.ndarray, np.ndarray, list[str], list[dict], list[dict]]:
    embedder = DinoEmbedder(device=device)

    embeddings = []
    labels = []
    hashes = []
    used_rows = []
    errors = []

    seen_hashes = set()

    for row in feedback_rows:
        image_path = resolve_image_path(
            image_path_raw=row["image_path"],
            images_root=images_root,
            csv_path=feedback_csv_path,
        )

        raw_label = row["correct_style_code"]
        label = normalize_feedback_label(raw_label)

        if label not in known_classes:
            errors.append(
                {
                    "feedback_id": row.get("feedback_id"),
                    "image_path": str(image_path),
                    "raw_label": raw_label,
                    "normalized_label": label,
                    "reason": "unknown_label",
                }
            )
            continue

        if not image_path.exists():
            errors.append(
                {
                    "feedback_id": row.get("feedback_id"),
                    "image_path": str(image_path),
                    "label": label,
                    "reason": "image_not_found",
                }
            )
            continue

        try:
            image_hash = file_sha256(image_path)

            if image_hash in seen_hashes:
                errors.append(
                    {
                        "feedback_id": row.get("feedback_id"),
                        "image_path": str(image_path),
                        "label": label,
                        "reason": "duplicate_in_feedback_batch",
                    }
                )
                continue

            seen_hashes.add(image_hash)

            img = Image.open(image_path).convert("RGB")

            if min(img.size) < 32:
                errors.append(
                    {
                        "feedback_id": row.get("feedback_id"),
                        "image_path": str(image_path),
                        "label": label,
                        "reason": "too_small",
                    }
                )
                continue

            emb = embedder.get_embedding(img)

            embeddings.append(emb)
            labels.append(label)
            hashes.append(image_hash)

            used_rows.append(
                {
                    "feedback_id": row.get("feedback_id"),
                    "image_path": str(image_path),
                    "correct_style_code": label,
                    "raw_correct_style_code": raw_label,
                    "image_hash": image_hash,
                }
            )

        except Exception as e:
            errors.append(
                {
                    "feedback_id": row.get("feedback_id"),
                    "image_path": str(image_path),
                    "label": label,
                    "reason": repr(e),
                }
            )

    if not embeddings:
        return (
            np.empty((0, EMBEDDING_DIM), dtype=np.float32),
            np.array([], dtype=str),
            [],
            [],
            errors,
        )

    return (
        np.vstack(embeddings).astype(np.float32),
        np.array(labels, dtype=str),
        hashes,
        used_rows,
        errors,
    )


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument("--base-feature-store", required=True)
    parser.add_argument("--feedback-csv", required=True)
    parser.add_argument("--model-bundle-dir", required=True)

    parser.add_argument(
        "--images-root",
        default=None,
        help="Optional root for relative image_path values from feedback CSV.",
    )

    parser.add_argument("--min-new-feedback", type=int, default=20)
    parser.add_argument("--feedback-repeat", type=int, default=3)

    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--label-smoothing", type=float, default=0.10)
    parser.add_argument("--class-weight-mode", default="inv_sqrt")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=10)

    parser.add_argument("--min-val-acc", type=float, default=0.60)
    parser.add_argument("--activate", action="store_true")

    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])

    args = parser.parse_args()

    base_feature_store = Path(args.base_feature_store)
    feedback_csv_path = Path(args.feedback_csv)
    bundle_dir = Path(args.model_bundle_dir)
    images_root = Path(args.images_root) if args.images_root else None

    bundle_dir.mkdir(parents=True, exist_ok=True)

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    print(f"device={device}")
    print(f"base_feature_store={base_feature_store}")
    print(f"feedback_csv={feedback_csv_path}")
    print(f"model_bundle_dir={bundle_dir}")
    print(f"images_root={images_root}")

    # -------------------------------------------------------------------------
    # Load base store
    # -------------------------------------------------------------------------
    base = np.load(base_feature_store, allow_pickle=True)

    X_base = base["embeddings"].astype(np.float32)
    y_base = base["labels"].astype(str)

    if X_base.ndim != 2 or X_base.shape[1] != EMBEDDING_DIM:
        raise ValueError(
            f"Expected embeddings shape [N, {EMBEDDING_DIM}], got {X_base.shape}"
        )

    if len(X_base) != len(y_base):
        raise ValueError(
            f"Embeddings/labels length mismatch: {len(X_base)} vs {len(y_base)}"
        )

    known_classes = set(np.unique(y_base))

    print(f"base_X={X_base.shape}")
    print(f"base_classes={sorted(known_classes)}")

    if "Contemporary_Art" not in known_classes:
        raise ValueError("Base feature store must contain Contemporary_Art")

    leaked = FORBIDDEN_FINAL_LABELS.intersection(known_classes)

    if leaked:
        raise ValueError(f"Base store still contains unmerged labels: {sorted(leaked)}")

    if len(known_classes) != 18:
        raise ValueError(
            f"Base feature store must contain exactly 18 classes, got {len(known_classes)}"
        )

    # -------------------------------------------------------------------------
    # Read feedback
    # -------------------------------------------------------------------------
    feedback_rows = read_feedback_csv(feedback_csv_path)

    if len(feedback_rows) < args.min_new_feedback:
        print(
            f"not_enough_feedback rows={len(feedback_rows)} "
            f"< min_new_feedback={args.min_new_feedback}"
        )
        return 0

    # -------------------------------------------------------------------------
    # Build feedback embeddings
    # -------------------------------------------------------------------------
    X_fb, y_fb, fb_hashes, used_feedback_rows, feedback_errors = build_feedback_features(
        feedback_rows=feedback_rows,
        known_classes=known_classes,
        device=device,
        feedback_csv_path=feedback_csv_path,
        images_root=images_root,
    )

    print(f"feedback_valid={len(X_fb)}")
    print(f"feedback_errors={len(feedback_errors)}")

    if len(X_fb) < args.min_new_feedback:
        print(
            f"not_enough_valid_feedback valid={len(X_fb)} "
            f"< min_new_feedback={args.min_new_feedback}"
        )
        return 0

    # -------------------------------------------------------------------------
    # Build unique dataset: base + valid feedback
    # -------------------------------------------------------------------------
    X_unique = np.vstack([X_base, X_fb]).astype(np.float32)
    y_unique_str = np.concatenate([y_base, y_fb]).astype(str)

    is_feedback = np.concatenate(
        [
            np.zeros(len(X_base), dtype=bool),
            np.ones(len(X_fb), dtype=bool),
        ]
    )

    le = LabelEncoder()
    y_unique = le.fit_transform(y_unique_str)

    num_classes = len(le.classes_)

    if num_classes != len(known_classes):
        raise ValueError(
            f"Class set changed unexpectedly: "
            f"base={len(known_classes)}, after_feedback={num_classes}"
        )

    if "Contemporary_Art" not in le.classes_:
        raise ValueError("Contemporary_Art disappeared after feedback merge")

    leaked_after = FORBIDDEN_FINAL_LABELS.intersection(set(le.classes_))
    if leaked_after:
        raise ValueError(f"Old unmerged labels found after feedback: {sorted(leaked_after)}")

    # -------------------------------------------------------------------------
    # Split before feedback_repeat to avoid leakage
    # -------------------------------------------------------------------------
    idx_all = np.arange(len(X_unique))

    idx_train, idx_val = train_test_split(
        idx_all,
        test_size=0.2,
        stratify=y_unique,
        random_state=args.seed,
    )

    train_feedback_mask = is_feedback[idx_train]

    X_train_base_part = X_unique[idx_train]
    y_train_base_part = y_unique[idx_train]

    X_val = X_unique[idx_val].astype(np.float32)
    y_val = y_unique[idx_val].astype(np.int64)

    X_train_feedback = X_unique[idx_train][train_feedback_mask]
    y_train_feedback = y_unique[idx_train][train_feedback_mask]

    if len(X_train_feedback) > 0 and args.feedback_repeat > 1:
        X_train_extra = np.repeat(
            X_train_feedback,
            repeats=args.feedback_repeat - 1,
            axis=0,
        )
        y_train_extra = np.repeat(
            y_train_feedback,
            repeats=args.feedback_repeat - 1,
            axis=0,
        )

        X_train = np.vstack([X_train_base_part, X_train_extra]).astype(np.float32)
        y_train = np.concatenate([y_train_base_part, y_train_extra]).astype(np.int64)
    else:
        X_train = X_train_base_part.astype(np.float32)
        y_train = y_train_base_part.astype(np.int64)

    print(f"train_unique={len(idx_train)}")
    print(f"train_after_feedback_repeat={len(X_train)}")
    print(f"val={len(idx_val)}")
    print(f"feedback_in_train={int(train_feedback_mask.sum())}")
    print(f"feedback_in_val={int(is_feedback[idx_val].sum())}")
    print(f"num_classes={num_classes}")
    print(f"classes={list(le.classes_)}")

    # -------------------------------------------------------------------------
    # Train head
    # -------------------------------------------------------------------------
    model, val_acc, val_preds, history = train_head(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        num_classes=num_classes,
        device=device,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        weight_decay=args.weight_decay,
        label_smoothing=args.label_smoothing,
        class_weight_mode=args.class_weight_mode,
        patience=args.patience,
        seed=args.seed,
    )

    report = classification_report(
        y_val,
        val_preds,
        target_names=le.classes_,
        output_dict=True,
        zero_division=0,
    )

    # -------------------------------------------------------------------------
    # Save bundle
    # -------------------------------------------------------------------------
    version = f"v_final_{FINAL_CONFIG_NAME}_{int(time.time())}"

    head_filename = f"head_{version}.pt"
    le_filename = f"label_encoder_{version}.joblib"
    meta_filename = f"meta_{version}.json"
    history_filename = f"history_{version}.json"
    feedback_features_filename = f"feedback_features_{version}.npz"
    used_feedback_filename = f"used_feedback_{version}.json"
    feedback_errors_filename = f"feedback_errors_{version}.json"
    val_predictions_filename = f"val_predictions_{version}.npz"

    head_path = bundle_dir / head_filename
    le_path = bundle_dir / le_filename
    meta_path = bundle_dir / meta_filename
    history_path = bundle_dir / history_filename
    feedback_features_path = bundle_dir / feedback_features_filename
    used_feedback_path = bundle_dir / used_feedback_filename
    feedback_errors_path = bundle_dir / feedback_errors_filename
    val_predictions_path = bundle_dir / val_predictions_filename

    torch.save(model.state_dict(), head_path)
    joblib.dump(le, le_path)

    np.savez(
        feedback_features_path,
        embeddings=X_fb.astype(np.float32),
        labels=y_fb.astype(str),
        image_hashes=np.array(fb_hashes, dtype=str),
    )

    np.savez(
        val_predictions_path,
        y_val=y_val.astype(np.int64),
        val_preds=val_preds.astype(np.int64),
        idx_val=idx_val.astype(np.int64),
        is_feedback_val=is_feedback[idx_val].astype(bool),
        classes=le.classes_.astype(str),
    )

    json_dump(history_path, history)
    json_dump(used_feedback_path, used_feedback_rows)
    json_dump(feedback_errors_path, feedback_errors)

    meta = {
        "version": version,
        "encoder": MODEL_NAME,
        "embedding_mode": EMBEDDING_MODE,
        "embedding_dim": int(EMBEDDING_DIM),

        "num_classes": int(num_classes),
        "classes": list(le.classes_),

        "class_grouping": CLASS_GROUPING,
        "display_names": DISPLAY_NAMES,
        "old_to_merged_label": OLD_TO_MERGED_LABEL,

        "head_path": head_filename,
        "label_encoder_path": le_filename,

        "base_feature_store": str(base_feature_store),
        "feedback_csv": str(feedback_csv_path),
        "feedback_features_path": feedback_features_filename,
        "used_feedback_path": used_feedback_filename,
        "feedback_errors_path": feedback_errors_filename,
        "val_predictions_path": val_predictions_filename,

        "n_base_samples": int(len(X_base)),
        "n_feedback_rows": int(len(feedback_rows)),
        "n_feedback_valid": int(len(X_fb)),
        "n_feedback_errors": int(len(feedback_errors)),
        "feedback_repeat": int(args.feedback_repeat),
        "n_unique_total_before_repeat": int(len(X_unique)),
        "n_train_unique": int(len(idx_train)),
        "n_train_after_repeat": int(len(X_train)),
        "n_val": int(len(idx_val)),
        "n_feedback_in_train": int(train_feedback_mask.sum()),
        "n_feedback_in_val": int(is_feedback[idx_val].sum()),

        "val_accuracy": round(float(val_acc), 4),
        "classification_report": report,

        "epochs": int(args.epochs),
        "batch_size": int(args.batch_size),
        "lr": float(args.lr),
        "weight_decay": float(args.weight_decay),
        "label_smoothing": float(args.label_smoothing),
        "class_weight_mode": args.class_weight_mode,
        "random_seed": int(args.seed),
        "min_val_acc": float(args.min_val_acc),
        "min_new_feedback": int(args.min_new_feedback),

        "history_path": history_filename,
        "trained_on": int(time.time()),
        "activated": False,
    }

    if args.activate and val_acc >= args.min_val_acc:
        meta["activated"] = True
        meta["current_meta_path"] = "current_meta.json"

    json_dump(meta_path, meta)

    if args.activate:
        if val_acc >= args.min_val_acc:
            current_meta_path = bundle_dir / "current_meta.json"
            atomic_copy(meta_path, current_meta_path)
            print(f"activated_current_meta={current_meta_path}")
        else:
            print(
                f"not_activated val_acc={val_acc:.4f} "
                f"< min_val_acc={args.min_val_acc:.4f}"
            )

    print(f"version={version}")
    print(f"meta_path={meta_path}")
    print(f"val_accuracy={val_acc:.4f}")
    print(f"feedback_valid={len(X_fb)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())