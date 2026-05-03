"""
Пример использования в backend:

    from inference import StyleClassifier

    clf = StyleClassifier.from_meta("model_bundle/meta.json")
    result = clf.predict("test_image.jpg")

    print(result)

Пример ответа:

    {
        "status": "ok",
        "style": "Impressionism",
        "confidence": 0.8342,
        "top_predictions": [
            {"style": "Impressionism", "confidence": 0.8342},
            {"style": "Post_Impressionism", "confidence": 0.0821},
            ...
        ],
        "model_version": "v_1712345678",
        "num_classes": 20,
        "use_tta": true,
        "use_ensemble": true
    }
"""

import argparse
import json
import sys
from pathlib import Path, PureWindowsPath
from typing import Optional, Union

import joblib
import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

try:
    import faiss
except Exception:
    faiss = None


# =============================================================================
# АРХИТЕКТУРА ГОЛОВЫ
# Должна совпадать с архитектурой, которая использовалась при обучении.
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


# =============================================================================
# TTA-ТРАНСФОРМЫ
# =============================================================================

def _center_crop(img: Image.Image, ratio: float = 0.85) -> Image.Image:
    w, h = img.size
    dw = int(w * (1 - ratio) / 2)
    dh = int(h * (1 - ratio) / 2)

    try:
        resample = Image.Resampling.BILINEAR
    except AttributeError:
        resample = Image.BILINEAR

    return img.crop((dw, dh, w - dw, h - dh)).resize((w, h), resample)


TTA_TRANSFORMS = [
    lambda img: img,
    lambda img: img.transpose(Image.FLIP_LEFT_RIGHT),
    lambda img: img.rotate(8, expand=False),
    lambda img: img.rotate(-8, expand=False),
    lambda img: _center_crop(img, ratio=0.85),
]


# =============================================================================
# ОСНОВНОЙ КЛАСС
# =============================================================================

class StyleClassifier:
    """
    Класс для инференса модели определения художественного стиля изображения.

    Загружает:
        - meta.json
        - DINOv2 encoder
        - ResidualStyleHead
        - LabelEncoder
        - FAISS index, если он есть и load_faiss=True

    Параметры
    ---------
    model_dir : str | Path
        Папка с model bundle.
    meta_filename : str
        Имя meta-файла.
    device : str | None
        "cuda" / "cpu". Если None, выбирается cuda при наличии.
    load_faiss : bool
        Загружать ли FAISS. Если FAISS недоступен, модель всё равно работает как MLP-only.
    verbose : bool
        Печатать ли логи загрузки.
    """

    def __init__(
        self,
        model_dir: Union[str, Path],
        meta_filename: str,
        device: Optional[str] = None,
        load_faiss: bool = True,
        verbose: bool = True,
    ):
        self.model_dir = Path(model_dir).expanduser().resolve()
        self.device = torch.device(
            device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self.load_faiss = bool(load_faiss)
        self.verbose = bool(verbose)

        self.meta: dict = {}
        self.processor = None
        self.encoder = None
        self.head = None
        self.le = None

        self.embedding_dim: int = 2048
        self.num_classes: int = 0

        self.faiss_index = None
        self.faiss_y: Optional[np.ndarray] = None

        self.best_alpha: float = 0.5
        self.best_k: int = 5

        self._load_all(meta_filename)


    @classmethod
    def from_meta(
        cls,
        meta_path: Union[str, Path],
        device: Optional[str] = None,
        load_faiss: bool = True,
        verbose: bool = True,
    ) -> "StyleClassifier":
        """
        Загрузка напрямую по пути к meta.json.

        Пример:
            clf = StyleClassifier.from_meta("model_bundle/meta.json")
        """
        p = Path(meta_path).expanduser().resolve()

        if not p.exists():
            raise FileNotFoundError(f"meta.json не найден: {p}")

        return cls(
            model_dir=p.parent,
            meta_filename=p.name,
            device=device,
            load_faiss=load_faiss,
            verbose=verbose,
        )

    # -------------------------------------------------------------------------
    # Логирование
    # -------------------------------------------------------------------------

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    # -------------------------------------------------------------------------
    # Работа с путями
    # -------------------------------------------------------------------------

    def _resolve_artifact(self, key: str, required: bool = True) -> Optional[Path]:
        """
        Достаёт путь к артефакту из meta.json.

        Поддерживает:
            - обычные Linux/Unix пути
            - Windows-пути вида D:\\wikiart_models_v2\\head.pt
            - относительные пути
            - просто имя файла

        Это нужно, потому что meta.json был создан на Windows,
        а backend работает внутри Linux Docker-контейнера.
        """
        if key not in self.meta:
            if required:
                raise KeyError(f"В meta.json отсутствует ключ: {key}")
            return None

        raw_value = str(self.meta[key])

        # Обычная интерпретация пути для текущей ОС
        raw_path = Path(raw_value)

        # Имя файла, если путь был Linux-style
        linux_name = raw_path.name

        # Имя файла, если путь был Windows-style: D:\folder\file.pt
        windows_name = PureWindowsPath(raw_value).name

        candidates = []

        if raw_path.is_absolute():
            candidates.append(raw_path)

        candidates.extend([
            self.model_dir / raw_path,
            self.model_dir / linux_name,
            self.model_dir / windows_name,
        ])

        # Убираем дубликаты
        unique_candidates = []
        seen = set()
        for candidate in candidates:
            candidate_str = str(candidate)
            if candidate_str not in seen:
                seen.add(candidate_str)
                unique_candidates.append(candidate)

        for candidate in unique_candidates:
            if candidate.exists():
                return candidate

        if required:
            checked = "\n".join(f"  - {p}" for p in unique_candidates)
            raise FileNotFoundError(
                f"Артефакт для ключа '{key}' не найден.\n"
                f"Значение в meta.json: {raw_value}\n"
                f"model_dir: {self.model_dir}\n"
                f"Проверенные пути:\n{checked}"
            )

        return None

    # -------------------------------------------------------------------------
    # Загрузка всех артефактов
    # -------------------------------------------------------------------------

    def _load_all(self, meta_filename: str) -> None:
        meta_path = self.model_dir / meta_filename

        if not meta_path.exists():
            raise FileNotFoundError(f"meta.json не найден: {meta_path}")

        with open(meta_path, "r", encoding="utf-8") as f:
            self.meta = json.load(f)

        version = self.meta.get("version", "unknown")
        encoder_name = self.meta.get("encoder", "facebook/dinov2-large")
        self.embedding_dim = int(self.meta.get("embedding_dim", 2048))

        self.num_classes = int(self.meta["num_classes"])

        self._log(f" Версия модели: {version}")
        self._log(f"   Энкодер: {encoder_name}")
        self._log(f"   Классов: {self.num_classes}")
        self._log(f"   embedding_dim: {self.embedding_dim}")
        val_metric = (
                self.meta.get("val_accuracy")
                or self.meta.get("val_acc_ensemble")
                or self.meta.get("val_acc")
                or "?"
        )

        test_metric = (
                self.meta.get("test_accuracy")
                or self.meta.get("test_acc_ensemble")
                or self.meta.get("test_acc")
                or "?"
        )

        self._log(f"   val_metric: {val_metric}")
        self._log(f"   test_metric: {test_metric}")

        # 1. DINOv2 encoder
        self._log(f" Загружаем энкодер {encoder_name} ...")

        self.processor = AutoImageProcessor.from_pretrained(encoder_name)
        self.encoder = AutoModel.from_pretrained(encoder_name).to(self.device)

        self.encoder.eval()
        for p in self.encoder.parameters():
            p.requires_grad = False

        self._log(f" Энкодер загружен | device={self.device}")

        # 2. ResidualStyleHead
        head_path = self._resolve_artifact("head_path", required=True)

        self.head = ResidualStyleHead(
            in_dim=self.embedding_dim,
            num_classes=self.num_classes,
        ).to(self.device)

        state = torch.load(head_path, map_location=self.device)

        # На случай если сохранён не чистый state_dict, а словарь с ключом state_dict.
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]

        self.head.load_state_dict(state)
        self.head.eval()

        self._log(f" Голова загружена: {head_path.name}")

        # 3. LabelEncoder
        le_path = self._resolve_artifact("label_encoder_path", required=True)
        self.le = joblib.load(le_path)

        if len(self.le.classes_) != self.num_classes:
            raise ValueError(
                "Несовпадение количества классов: "
                f"meta num_classes={self.num_classes}, "
                f"label_encoder classes={len(self.le.classes_)}"
            )

        self._log(f" LabelEncoder загружен: {le_path.name}")

        # 4. FAISS, если доступен
        self.faiss_index = None
        self.faiss_y = None

        if not self.load_faiss:
            self._log(" FAISS отключён параметром load_faiss=False")
        elif faiss is None:
            self._log(" faiss не установлен. Будет использоваться только MLP.")
        else:
            faiss_path = self._resolve_artifact("faiss_index_path", required=False)
            faiss_y_path = self._resolve_artifact("faiss_y_index_path", required=False)

            if faiss_path is None or faiss_y_path is None:
                self._log(" FAISS-файлы не найдены. Будет использоваться только MLP.")
            else:
                self.faiss_index = faiss.read_index(str(faiss_path))
                self.faiss_y = np.load(faiss_y_path).astype(np.int64)

                if self.faiss_index.d != self.embedding_dim:
                    raise ValueError(
                        f"Размерность FAISS не совпадает с embedding_dim: "
                        f"faiss.d={self.faiss_index.d}, embedding_dim={self.embedding_dim}"
                    )

                if len(self.faiss_y) != self.faiss_index.ntotal:
                    raise ValueError(
                        f"Размер faiss_y не совпадает с FAISS index: "
                        f"len(faiss_y)={len(self.faiss_y)}, "
                        f"index.ntotal={self.faiss_index.ntotal}"
                    )

                self._log(f" FAISS загружен: {self.faiss_index.ntotal} векторов")

        self.best_alpha = float(self.meta.get("best_alpha", 0.5))
        self.best_k = int(self.meta.get("best_k", 5))

        self._log(f"   best_alpha: {self.best_alpha}")
        self._log(f"   best_k: {self.best_k}")

    # -------------------------------------------------------------------------
    # Embedding
    # -------------------------------------------------------------------------

    @torch.no_grad()
    def _get_embedding(self, pil_image: Image.Image) -> np.ndarray:
        """
        PIL Image → L2-нормированный cls_mean embedding.

        Для DINOv2-large:
            CLS token      = 1024
            mean patches   = 1024
            итоговый вектор = 2048
        """
        image = pil_image.convert("RGB")

        inputs = self.processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        out = self.encoder(**inputs)
        hidden = out.last_hidden_state

        cls = hidden[:, 0]
        patches = hidden[:, 1:].mean(dim=1)

        emb = torch.cat([cls, patches], dim=-1)
        emb = emb.squeeze(0).detach().cpu().numpy().astype(np.float32)

        norm = np.linalg.norm(emb) + 1e-12
        emb = emb / norm

        return emb.astype(np.float32)

    # -------------------------------------------------------------------------
    # FAISS KNN probabilities
    # -------------------------------------------------------------------------

    def _knn_probs(self, indices: np.ndarray, scores: np.ndarray) -> np.ndarray:
        """
        FAISS-соседи → вероятности классов.
        """
        probs = np.zeros(self.num_classes, dtype=np.float32)

        if self.faiss_y is None:
            return probs

        valid = indices[0] >= 0
        valid_indices = indices[0][valid]

        if len(valid_indices) == 0:
            return probs

        labels = self.faiss_y[valid_indices].astype(np.int64)

        weights = np.clip(scores[0][valid], 0.0, None).astype(np.float32)

        if weights.sum() < 1e-12:
            weights = np.ones_like(weights, dtype=np.float32)

        probs = np.bincount(
            labels,
            weights=weights,
            minlength=self.num_classes,
        ).astype(np.float32)

        probs = probs / (probs.sum() + 1e-12)

        return probs

    # -------------------------------------------------------------------------
    # Predict
    # -------------------------------------------------------------------------

    @torch.no_grad()
    def predict(
        self,
        image: Union[str, Path, Image.Image],
        use_tta: bool = True,
        use_ensemble: bool = True,
        top_n: int = 5,
    ) -> dict:
        """
        Предсказать стиль изображения.

        Параметры
        ---------
        image : str | Path | PIL.Image
            Путь к изображению или PIL.Image.
        use_tta : bool
            Использовать TTA: original, flip, rotations, center crop.
        use_ensemble : bool
            Смешивать MLP с FAISS KNN, если FAISS загружен.
        top_n : int
            Сколько классов вернуть в top_predictions.

        Возвращает
        ----------
        dict:
            {
                "status": "ok",
                "style": "...",
                "confidence": 0.1234,
                "top_predictions": [...],
                "model_version": "...",
                "num_classes": 20,
                "use_tta": true,
                "use_ensemble": true
            }
        """
        if top_n < 1:
            raise ValueError("top_n должен быть >= 1")

        top_n = min(int(top_n), self.num_classes)

        # 1. Открываем изображение
        if isinstance(image, (str, Path)):
            path = Path(image).expanduser()

            if not path.exists():
                raise FileNotFoundError(f"Файл не найден: {path}")

            with Image.open(path) as img:
                pil = img.convert("RGB")

        elif isinstance(image, Image.Image):
            pil = image.convert("RGB")
        else:
            raise TypeError(
                f"image должен быть str, Path или PIL.Image, получено: {type(image)}"
            )

        # 2. Минимальная проверка размера
        if min(pil.size) < 32:
            raise ValueError(
                f"Изображение слишком маленькое: {pil.size}. Минимум 32x32."
            )

        # 3. TTA
        transforms = TTA_TRANSFORMS if use_tta else [lambda img: img]

        all_logits = []
        all_embs = []

        for transform in transforms:
            aug = transform(pil)
            emb = self._get_embedding(aug)
            all_embs.append(emb)

            x = torch.tensor(
                emb,
                dtype=torch.float32,
                device=self.device,
            ).unsqueeze(0)

            logits = self.head(x).detach().cpu()
            all_logits.append(logits)

        avg_logits = torch.stack(all_logits).mean(dim=0)
        mlp_probs = torch.softmax(avg_logits, dim=-1).squeeze(0).numpy().astype(np.float32)

        final_probs = mlp_probs.copy()

        # 4. FAISS ensemble
        ensemble_used = (
            bool(use_ensemble)
            and self.faiss_index is not None
            and self.faiss_y is not None
            and self.faiss_index.ntotal > 0
        )

        if ensemble_used:
            mean_emb = np.stack(all_embs).mean(axis=0).astype(np.float32)
            mean_emb = mean_emb / (np.linalg.norm(mean_emb) + 1e-12)

            k = min(self.best_k, self.faiss_index.ntotal)

            scores, indices = self.faiss_index.search(
                mean_emb.reshape(1, -1).astype(np.float32),
                k,
            )

            knn_probs = self._knn_probs(indices, scores)

            final_probs = (
                self.best_alpha * mlp_probs
                + (1.0 - self.best_alpha) * knn_probs
            ).astype(np.float32)

            final_probs = np.clip(final_probs, 0.0, None)
            final_probs = final_probs / (final_probs.sum() + 1e-12)

        # 5. Формируем ответ
        sorted_idx = np.argsort(final_probs)[::-1]

        top_predictions = []

        for i in sorted_idx[:top_n]:
            style_name = str(self.le.inverse_transform([int(i)])[0])
            conf = round(float(final_probs[i]), 4)

            top_predictions.append(
                {
                    "style": style_name,
                    "confidence": conf,
                }
            )

        return {
            "status": "ok",
            "style": top_predictions[0]["style"],
            "confidence": top_predictions[0]["confidence"],
            "top_predictions": top_predictions,
            "model_version": self.meta.get("version", "unknown"),
            "num_classes": int(self.num_classes),
            "use_tta": bool(use_tta),
            "use_ensemble": bool(ensemble_used),
        }

    # -------------------------------------------------------------------------
    # Safe predict для backend
    # -------------------------------------------------------------------------

    def predict_safe(
        self,
        image: Union[str, Path, Image.Image],
        use_tta: bool = True,
        use_ensemble: bool = True,
        top_n: int = 5,
    ) -> dict:
        """
        Безопасная обёртка для backend.
        Вместо исключения возвращает JSON со status='error'.
        """
        try:
            return self.predict(
                image=image,
                use_tta=use_tta,
                use_ensemble=use_ensemble,
                top_n=top_n,
            )
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "model_version": self.meta.get("version", "unknown"),
            }

    # -------------------------------------------------------------------------
    # repr
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"StyleClassifier("
            f"encoder={self.meta.get('encoder', 'unknown')}, "
            f"classes={self.num_classes}, "
            f"device={self.device}, "
            f"faiss={'yes' if self.faiss_index is not None else 'no'}"
            f")"
        )


# =============================================================================
# CLI
# =============================================================================

def _find_meta(model_path: Union[str, Path]) -> Path:
    """
    Разрешает варианты:
        1. путь прямо к meta.json
        2. путь к папке model_bundle/
    """
    p = Path(model_path).expanduser().resolve()

    if p.is_file():
        return p

    if not p.exists():
        raise FileNotFoundError(f"Путь не найден: {p}")

    meta_default = p / "meta.json"
    if meta_default.exists():
        return meta_default

    metas = sorted(p.glob("meta_*.json"))

    if not metas:
        metas = sorted(p.glob("meta*.json"))

    if not metas:
        raise FileNotFoundError(f"Не найден meta.json или meta_*.json в папке: {p}")

    return metas[-1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inference для системы определения стиля изображения."
    )

    parser.add_argument(
        "model",
        type=str,
        help="Путь к папке model_bundle или к meta.json/meta_*.json",
    )

    parser.add_argument(
        "image",
        type=str,
        help="Путь к изображению",
    )

    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["cpu", "cuda"],
        help="Устройство: cpu или cuda. По умолчанию выбирается автоматически.",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Сколько top-предсказаний вывести.",
    )

    parser.add_argument(
        "--no-tta",
        action="store_true",
        help="Отключить TTA.",
    )

    parser.add_argument(
        "--no-ensemble",
        action="store_true",
        help="Отключить FAISS ensemble и использовать только MLP.",
    )

    args = parser.parse_args()

    try:
        meta_path = _find_meta(args.model)
        print(f" Используем meta: {meta_path}")

        clf = StyleClassifier.from_meta(
            meta_path,
            device=args.device,
            load_faiss=not args.no_ensemble,
            verbose=True,
        )

        print()
        result = clf.predict_safe(
            args.image,
            use_tta=not args.no_tta,
            use_ensemble=not args.no_ensemble,
            top_n=args.top_n,
        )

        if result["status"] != "ok":
            print(f" Ошибка: {result['message']}")
            sys.exit(1)

        print(f"\n Стиль:       {result['style']}")
        print(f"   Уверенность: {result['confidence'] * 100:.1f}%")
        print(f"   Версия:      {result['model_version']}")
        print(f"   TTA:         {result['use_tta']}")
        print(f"   Ensemble:    {result['use_ensemble']}")

        print(f"\n   Top-{len(result['top_predictions'])}:")
        for i, item in enumerate(result["top_predictions"], 1):
            bar = "█" * int(item["confidence"] * 30)
            print(
                f"   {i}. {item['style']:<35} "
                f"{item['confidence'] * 100:5.1f}%  {bar}"
            )

    except Exception as e:
        print(f"Ошибка запуска inference: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
