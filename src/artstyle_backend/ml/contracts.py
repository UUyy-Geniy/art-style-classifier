from __future__ import annotations

from pydantic import BaseModel, Field


class ModelPrediction(BaseModel):
    style_code: str
    confidence: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)

