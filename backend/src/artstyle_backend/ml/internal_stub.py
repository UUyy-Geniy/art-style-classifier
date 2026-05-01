from __future__ import annotations

import hashlib

from artstyle_backend.ml.contracts import ModelPrediction


class InternalStubModel:
    def __init__(self, style_codes: list[str]) -> None:
        if not style_codes:
            raise ValueError("Stub model requires at least one style code.")
        self._style_codes = style_codes

    def predict(self, image_bytes: bytes, top_k: int) -> list[dict]:
        scores: list[tuple[str, float]] = []
        for style_code in self._style_codes:
            digest = hashlib.sha256(image_bytes + style_code.encode("utf-8")).digest()
            raw_score = int.from_bytes(digest[:8], byteorder="big") / (2**64)
            scores.append((style_code, raw_score + 1e-9))

        total_score = sum(score for _, score in scores)
        ranked = sorted(scores, key=lambda item: item[1], reverse=True)[:top_k]
        predictions = [
            ModelPrediction(
                style_code=style_code,
                confidence=score / total_score,
                rank=index,
            ).model_dump()
            for index, (style_code, score) in enumerate(ranked, start=1)
        ]
        return predictions

