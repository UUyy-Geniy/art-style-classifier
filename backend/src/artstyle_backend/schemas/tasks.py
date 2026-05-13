from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from artstyle_backend.domain import TaskStatus


class UploadAcceptedResponse(BaseModel):
    task_id: str
    status: TaskStatus
    s3_key: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


class StyleResponse(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None


class PredictionCandidateResponse(BaseModel):
    rank: int
    confidence: float
    style: StyleResponse


class PredictionResultResponse(BaseModel):
    task_id: str
    status: TaskStatus
    image_s3_key: str
    image_url: str | None = None
    model_name: str
    model_version: str
    model_source: str
    top_prediction: PredictionCandidateResponse
    top_k: list[PredictionCandidateResponse] = Field(default_factory=list)
    completed_at: datetime


class PredictionFeedbackRequest(BaseModel):
    correct_style_code: str
    notes: str | None = Field(default=None, max_length=2000)


class PredictionFeedbackResponse(BaseModel):
    feedback_id: int
    task_id: str
    correct_style_code: str
    predicted_style_code: str
    model_version: str
    status: str
    used_in_training: bool
    created_at: datetime
