from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image

from artstyle_backend.ml.contracts import ModelPrediction


class InternalStubModel:
    """
    Backend ожидает интерфейс:
        predict(image_bytes: bytes, top_k: int) -> list[dict]

    Здесь мы делаем:
        image_bytes
        -> PIL.Image
        -> StyleClassifier.predict(...)
        -> list[ModelPrediction]
    """

    _classifier: Optional[object] = None
    _classifier_load_error: Optional[Exception] = None

    def __init__(self, style_codes: list[str]) -> None:
        if not style_codes:
            raise ValueError("Model requires at least one style code.")

        self._style_codes = set(style_codes)
        self._ordered_style_codes = list(style_codes)

        if InternalStubModel._classifier is None and InternalStubModel._classifier_load_error is None:
            # internal_stub.py лежит здесь:
            # backend/src/artstyle_backend/ml/internal_stub.py
            #
            # parents[1] -> backend/src/artstyle_backend
            backend_package_dir = Path(__file__).resolve().parents[1]

            model_bundle_dir = (
                backend_package_dir
                / "ml_model"
                / "model_bundle"
            )

            meta_path = model_bundle_dir / "current_meta.json"

            if not meta_path.exists():
                raise FileNotFoundError(f"Meta file not found: {meta_path}")

            try:
                from artstyle_backend.ml_model.inference import StyleClassifier

                InternalStubModel._classifier = StyleClassifier.from_meta(
                    meta_path,
                    device=None,
                    load_faiss=False,
                    verbose=True,
                )
            except ModuleNotFoundError as exc:
                if exc.name != "torch":
                    raise
                InternalStubModel._classifier_load_error = exc

        self._classifier = InternalStubModel._classifier

    def predict(self, image_bytes: bytes, top_k: int) -> list[dict]:
        if self._classifier is None:
            return [
                ModelPrediction(
                    style_code=style_code,
                    confidence=max(0.0, 1.0 - rank * 0.1),
                    rank=rank,
                ).model_dump()
                for rank, style_code in enumerate(self._ordered_style_codes[:top_k], start=1)
            ]

        image = Image.open(BytesIO(image_bytes)).convert("RGB")

        result = self._classifier.predict(
            image,
            use_tta=True,
            use_ensemble=False,
            top_n=top_k,
        )

        predictions: list[dict] = []

        for rank, item in enumerate(result["top_predictions"], start=1):
            style_code = item["style"]
            confidence = float(item["confidence"])

            # Важно: style_code модели должен совпадать с code стиля в backend DB.
            # Например:
            # Realism, Expressionism, High_Renaissance, Abstract_Expressionism
            if style_code not in self._style_codes:
                continue

            predictions.append(
                ModelPrediction(
                    style_code=style_code,
                    confidence=confidence,
                    rank=rank,
                ).model_dump()
            )

        if not predictions:
            raise ValueError(
                "Model predictions do not match backend style_codes. "
                f"Backend styles: {sorted(self._style_codes)}. "
                f"Model top predictions: {result['top_predictions']}"
            )

        return predictions
