from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from artstyle_backend.api.deps import get_storage
from artstyle_backend.core.database import get_db_session
from artstyle_backend.domain import TaskStatus
from artstyle_backend.schemas.tasks import (
    PredictionFeedbackRequest,
    PredictionFeedbackResponse,
    PredictionResultResponse,
    TaskStatusResponse,
)
from artstyle_backend.services.storage import StorageService
from artstyle_backend.services.tasks import (
    assemble_prediction_response,
    get_task_status_or_404,
    get_task_with_prediction_or_404,
    save_prediction_feedback,
)

router = APIRouter()


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskStatusResponse:
    task = await get_task_status_or_404(session, task_id)
    return TaskStatusResponse(
        task_id=task.id,
        status=task.status,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        error_message=task.error_message,
    )


@router.get("/tasks/{task_id}/result", response_model=PredictionResultResponse)
async def get_task_result(
    task_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[StorageService, Depends(get_storage)],
) -> PredictionResultResponse:
    task = await get_task_with_prediction_or_404(session, task_id)
    if task.status != TaskStatus.SUCCEEDED.value or task.prediction is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prediction result is not ready yet.",
        )
    return assemble_prediction_response(task, storage)


@router.post("/tasks/{task_id}/feedback", response_model=PredictionFeedbackResponse)
async def submit_prediction_feedback(
    task_id: str,
    payload: PredictionFeedbackRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PredictionFeedbackResponse:
    feedback = await save_prediction_feedback(
        session=session,
        task_id=task_id,
        correct_style_code=payload.correct_style_code,
        notes=payload.notes,
    )
    prediction = feedback.prediction
    return PredictionFeedbackResponse(
        feedback_id=feedback.id,
        task_id=feedback.task_id,
        correct_style_code=feedback.correct_style.code,
        predicted_style_code=prediction.top_style.code,
        model_version=prediction.model_version,
        status=feedback.status,
        used_in_training=feedback.used_in_training,
        created_at=feedback.created_at,
    )
