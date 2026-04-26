from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from artstyle_backend.domain import ModelSource


class CurrentModelResponse(BaseModel):
    model_name: str
    model_version: str
    model_source: str
    revision: int
    updated_at: datetime


class AvailableModelResponse(BaseModel):
    model_name: str
    model_version: str
    model_source: str
    current_stage: str | None = None
    aliases: list[str] = Field(default_factory=list)
    is_active: bool = False


class ModelSwitchRequest(BaseModel):
    model_name: str | None = None
    model_version: str
    model_source: ModelSource = ModelSource.MLFLOW


class AdminActionResponse(BaseModel):
    status: str
    model_name: str
    model_version: str
    model_source: str
    revision: int


class RetrainExportResponse(BaseModel):
    export_id: int
    export_key: str
    records_count: int
    created_at: datetime

