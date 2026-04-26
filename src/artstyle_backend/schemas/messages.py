from __future__ import annotations

from pydantic import BaseModel


class InferenceTaskMessage(BaseModel):
    task_id: str
    s3_key: str
    top_k: int

