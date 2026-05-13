from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from artstyle_backend.api.deps import get_app_settings, get_storage, verify_admin_token
from artstyle_backend.core.config import Settings
from artstyle_backend.core.database import get_db_session
from artstyle_backend.schemas.admin import (
    AdminActionResponse,
    AvailableModelResponse,
    CurrentModelResponse,
    ModelSwitchRequest,
    RetrainExportResponse,
    RetrainRunRequest,
    RetrainRunResponse,
)
from artstyle_backend.services.bootstrap import ensure_seed_data
from artstyle_backend.services.model_registry import (
    MlflowRegistryClient,
    bump_model_revision,
    get_active_model_state,
    list_available_models,
    switch_active_model,
)
from artstyle_backend.services.retrain_export import create_retrain_export
from artstyle_backend.services.storage import StorageService

router = APIRouter(dependencies=[Depends(verify_admin_token)])
logger = logging.getLogger(__name__)


@dataclass
class RetrainJob:
    job_id: str
    status: str
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


_retrain_jobs: dict[str, RetrainJob] = {}
_retrain_process: asyncio.subprocess.Process | None = None


def _tail(value: str, limit: int = 12000) -> str:
    return value[-limit:]


async def _append_stream(
    stream: asyncio.StreamReader | None,
    job: RetrainJob,
    field_name: str,
) -> None:
    if stream is None:
        return

    while True:
        chunk = await stream.readline()
        if not chunk:
            break
        current = getattr(job, field_name)
        setattr(job, field_name, _tail(current + chunk.decode("utf-8", errors="replace")))


async def _run_retrain_job(job: RetrainJob) -> None:
    global _retrain_process

    logger.info("Starting feedback retrain job %s", job.job_id)
    try:
        process = await asyncio.create_subprocess_exec(
            *job.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _retrain_process = process
        await asyncio.gather(
            _append_stream(process.stdout, job, "stdout"),
            _append_stream(process.stderr, job, "stderr"),
        )
        job.exit_code = await process.wait()
        job.status = "succeeded" if job.exit_code == 0 else "failed"
    except Exception as exc:  # pragma: no cover - defensive guard for background task
        logger.exception("Feedback retrain job %s crashed", job.job_id)
        job.status = "failed"
        job.stderr = _tail(f"{job.stderr}\n{type(exc).__name__}: {exc}\n")
        job.exit_code = -1
    finally:
        if _retrain_process is not None and _retrain_process.returncode is not None:
            _retrain_process = None
        job.finished_at = datetime.now(UTC)
        logger.info(
            "Feedback retrain job %s finished with status=%s exit_code=%s",
            job.job_id,
            job.status,
            job.exit_code,
        )


def _job_response(job: RetrainJob) -> RetrainRunResponse:
    return RetrainRunResponse(
        status=job.status,
        job_id=job.job_id,
        command=job.command,
        exit_code=job.exit_code,
        stdout=job.stdout,
        stderr=job.stderr,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/models/current", response_model=CurrentModelResponse)
async def get_current_model(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentModelResponse:
    state = await get_active_model_state(session)
    if state is None:
        await ensure_seed_data(session)
        state = await get_active_model_state(session)
    if state is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No model state.")
    return CurrentModelResponse.model_validate(state, from_attributes=True)


@router.get("/models/available", response_model=list[AvailableModelResponse])
async def get_available_models(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> list[AvailableModelResponse]:
    state = await get_active_model_state(session)
    client = MlflowRegistryClient(settings)
    descriptors = await asyncio.to_thread(
        list_available_models,
        client,
        state.model_name if state else settings.default_model_name,
        state.model_version if state else settings.default_model_version,
        state.model_source if state else settings.default_model_source,
    )
    return [AvailableModelResponse.model_validate(item) for item in descriptors]


@router.post("/models/switch", response_model=AdminActionResponse)
async def switch_model(
    payload: ModelSwitchRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AdminActionResponse:
    client = MlflowRegistryClient(settings)
    try:
        state = await switch_active_model(
            session=session,
            registry_client=client,
            model_name=payload.model_name or settings.default_model_name,
            model_version=payload.model_version,
            model_source=payload.model_source.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AdminActionResponse(
        status="ok",
        model_name=state.model_name,
        model_version=state.model_version,
        model_source=state.model_source,
        revision=state.revision,
    )


@router.post("/models/reload-workers", response_model=AdminActionResponse)
async def reload_workers(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminActionResponse:
    state = await bump_model_revision(session)
    if state is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No model state.")
    return AdminActionResponse(
        status="ok",
        model_name=state.model_name,
        model_version=state.model_version,
        model_source=state.model_source,
        revision=state.revision,
    )


@router.post("/retrain/export", response_model=RetrainExportResponse)
async def export_retrain_dataset(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[StorageService, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> RetrainExportResponse:
    export = await create_retrain_export(session, storage, settings)
    return RetrainExportResponse.model_validate(export, from_attributes=True)


@router.post("/retrain/run", response_model=RetrainRunResponse)
async def run_retrain_from_feedback(
    payload: RetrainRunRequest,
) -> RetrainRunResponse:
    running_job = next((job for job in _retrain_jobs.values() if job.status == "running"), None)
    if running_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Retrain job is already running: {running_job.job_id}",
        )

    package_dir = Path(__file__).resolve().parents[2]
    retrain_script = package_dir / "ml_model" / "retrain_from_feedback.py"
    model_bundle_dir = package_dir / "ml_model" / "model_bundle"
    base_feature_store = model_bundle_dir / "features_large_cls_mean_top18_contemporary_merged_v1.npz"
    feedback_csv = Path(payload.feedback_csv)

    if not feedback_csv.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Feedback CSV not found: {feedback_csv}",
        )
    if not base_feature_store.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Base feature store not found: {base_feature_store}",
        )

    command = [
        sys.executable,
        str(retrain_script),
        "--base-feature-store",
        str(base_feature_store),
        "--feedback-csv",
        str(feedback_csv),
        "--model-bundle-dir",
        str(model_bundle_dir),
        "--min-new-feedback",
        str(payload.min_new_feedback),
        "--feedback-repeat",
        str(payload.feedback_repeat),
        "--epochs",
        str(payload.epochs),
        "--batch-size",
        str(payload.batch_size),
        "--min-val-acc",
        str(payload.min_val_acc),
        "--device",
        payload.device,
    ]
    if payload.activate:
        command.append("--activate")

    job = RetrainJob(job_id=str(uuid4()), status="running", command=command)
    _retrain_jobs[job.job_id] = job
    asyncio.create_task(_run_retrain_job(job))
    return _job_response(job)


@router.get("/retrain/jobs/{job_id}", response_model=RetrainRunResponse)
async def get_retrain_job(job_id: str) -> RetrainRunResponse:
    job = _retrain_jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Retrain job not found: {job_id}",
        )
    return _job_response(job)


@router.get("/retrain/jobs", response_model=list[RetrainRunResponse])
async def list_retrain_jobs() -> list[RetrainRunResponse]:
    jobs = sorted(_retrain_jobs.values(), key=lambda item: item.started_at, reverse=True)
    return [_job_response(job) for job in jobs[:20]]
