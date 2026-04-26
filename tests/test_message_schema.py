from __future__ import annotations

from artstyle_backend.schemas.messages import InferenceTaskMessage


def test_inference_task_message_roundtrip() -> None:
    message = InferenceTaskMessage(task_id="task-1", s3_key="uploads/a.png", top_k=5)
    raw = message.model_dump_json()
    restored = InferenceTaskMessage.model_validate_json(raw)

    assert restored == message

