from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ModelSource(str, Enum):
    INTERNAL_STUB = "internal_stub"
    MLFLOW = "mlflow"


class AdminActionType(str, Enum):
    SWITCH_MODEL = "switch_model"
    RELOAD_WORKERS = "reload_workers"
    EXPORT_RETRAIN = "export_retrain"

