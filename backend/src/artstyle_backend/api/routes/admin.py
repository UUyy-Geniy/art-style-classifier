from __future__ import annotations

import asyncio
from typing import Annotated

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
) -> RetrainExportResponse:
    export = await create_retrain_export(session, storage)
    return RetrainExportResponse.model_validate(export, from_attributes=True)

