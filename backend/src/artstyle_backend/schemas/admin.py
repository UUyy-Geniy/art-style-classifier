from __future__ import annotations

from datetime import datetime
from typing import Any

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
    export_id: int = Field(validation_alias="id")
    export_key: str
    records_count: int
    payload_preview: dict[str, Any] | None = None
    created_at: datetime


class RetrainRunRequest(BaseModel):
    feedback_csv: str
    min_new_feedback: int = Field(default=20, ge=1)
    feedback_repeat: int = Field(default=3, ge=1)
    epochs: int = Field(default=30, ge=1)
    batch_size: int = Field(default=256, ge=1)
    min_val_acc: float = Field(default=0.60, ge=0.0, le=1.0)
    device: str = Field(default="auto", pattern="^(auto|cpu|cuda)$")
    activate: bool = False


class RetrainRunResponse(BaseModel):
    status: str
    job_id: str
    command: list[str]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    started_at: datetime
    finished_at: datetime | None = None
