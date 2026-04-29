from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePath
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from artstyle_backend.db.models import InferenceTask, Prediction, PredictionCandidate, Style
from artstyle_backend.domain import TaskStatus
from artstyle_backend.messaging.publisher import RabbitMQPublisher
from artstyle_backend.schemas.messages import InferenceTaskMessage
from artstyle_backend.schemas.tasks import (
    PredictionCandidateResponse,
    PredictionResultResponse,
    StyleResponse,
)
from artstyle_backend.services.storage import StorageService


def build_storage_key(task_id: str, filename: str) -> str:
    safe_name = PurePath(filename).name.replace(" ", "_")
    date_prefix = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"uploads/{date_prefix}/{task_id}/{safe_name}"


async def create_inference_task(
    session: AsyncSession,
    storage: StorageService,
    publisher: RabbitMQPublisher,
    settings,
    filename: str,
    content_type: str,
    payload: bytes,
) -> InferenceTask:
    task_id = str(uuid4())
    s3_key = build_storage_key(task_id, filename)

    await storage.upload_bytes(s3_key, payload, content_type)

    task = InferenceTask(
        id=task_id,
        status=TaskStatus.QUEUED.value,
        s3_key=s3_key,
        original_filename=filename,
        mime_type=content_type,
        file_size=len(payload),
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)

    try:
        await publisher.publish_task(
            InferenceTaskMessage(task_id=task.id, s3_key=task.s3_key, top_k=settings.default_top_k)
        )
    except Exception as exc:
        task.status = TaskStatus.FAILED.value
        task.error_message = "Failed to publish task into RabbitMQ."
        task.finished_at = datetime.now(timezone.utc)
        await session.commit()
        raise RuntimeError("Could not queue inference task.") from exc

    return task


async def get_task_status_or_404(session: AsyncSession, task_id: str) -> InferenceTask:
    task = await session.get(InferenceTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


async def get_task_with_prediction_or_404(session: AsyncSession, task_id: str) -> InferenceTask:
    query = (
        select(InferenceTask)
        .where(InferenceTask.id == task_id)
        .options(
            selectinload(InferenceTask.prediction)
            .selectinload(Prediction.top_style),
            selectinload(InferenceTask.prediction)
            .selectinload(Prediction.candidates)
            .selectinload(PredictionCandidate.style),
        )
    )
    task = (await session.execute(query)).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    return task


async def mark_task_processing(session: AsyncSession, task_id: str) -> InferenceTask:
    task = await get_task_status_or_404(session, task_id)
    task.status = TaskStatus.PROCESSING.value
    task.started_at = datetime.now(timezone.utc)
    task.error_message = None
    await session.commit()
    await session.refresh(task)
    return task


async def mark_task_failed(session: AsyncSession, task_id: str, error_message: str) -> None:
    task = await get_task_status_or_404(session, task_id)
    task.status = TaskStatus.FAILED.value
    task.error_message = error_message[:2000]
    task.finished_at = datetime.now(timezone.utc)
    await session.commit()


async def persist_prediction_result(
    session: AsyncSession,
    task_id: str,
    model_name: str,
    model_version: str,
    model_source: str,
    candidates_payload: list[dict],
) -> None:
    task = await get_task_status_or_404(session, task_id)
    style_codes = [item["style_code"] for item in candidates_payload]
    styles = (
        await session.execute(select(Style).where(Style.code.in_(style_codes)))
    ).scalars().all()
    styles_by_code = {style.code: style for style in styles}

    missing_codes = [code for code in style_codes if code not in styles_by_code]
    if missing_codes:
        raise ValueError(f"Unknown style codes from model output: {missing_codes}")

    top_candidate = min(candidates_payload, key=lambda item: item["rank"])
    prediction = Prediction(
        task_id=task.id,
        top_style_id=styles_by_code[top_candidate["style_code"]].id,
        top_confidence=top_candidate["confidence"],
        model_name=model_name,
        model_version=model_version,
        model_source=model_source,
        raw_response={"top_k": candidates_payload},
    )
    session.add(prediction)
    await session.flush()

    for candidate in candidates_payload:
        session.add(
            PredictionCandidate(
                prediction_id=prediction.id,
                style_id=styles_by_code[candidate["style_code"]].id,
                rank=candidate["rank"],
                confidence=candidate["confidence"],
            )
        )

    task.status = TaskStatus.SUCCEEDED.value
    task.finished_at = datetime.now(timezone.utc)
    await session.commit()


def assemble_prediction_response(task: InferenceTask, storage: StorageService) -> PredictionResultResponse:
    prediction = task.prediction
    assert prediction is not None

    def map_candidate(candidate: PredictionCandidate) -> PredictionCandidateResponse:
        return PredictionCandidateResponse(
            rank=candidate.rank,
            confidence=candidate.confidence,
            style=StyleResponse(
                id=candidate.style.id,
                code=candidate.style.code,
                name=candidate.style.name,
                description=candidate.style.description,
            ),
        )

    candidates = [map_candidate(candidate) for candidate in prediction.candidates]
    top_prediction = min(candidates, key=lambda item: item.rank)
    return PredictionResultResponse(
        task_id=task.id,
        status=task.status,
        image_s3_key=task.s3_key,
        image_url=storage.build_presigned_get_url(task.s3_key),
        model_name=prediction.model_name,
        model_version=prediction.model_version,
        model_source=prediction.model_source,
        top_prediction=top_prediction,
        top_k=candidates,
        completed_at=task.finished_at or prediction.created_at,
    )

