from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from artstyle_backend.api.deps import get_app_settings, get_publisher, get_storage
from artstyle_backend.core.config import Settings
from artstyle_backend.core.database import get_db_session
from artstyle_backend.messaging.publisher import RabbitMQPublisher
from artstyle_backend.schemas.tasks import UploadAcceptedResponse
from artstyle_backend.services.storage import StorageService
from artstyle_backend.services.tasks import create_inference_task
from artstyle_backend.services.uploads import UploadValidationError, validate_upload_payload

router = APIRouter()


@router.post("/upload", response_model=UploadAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_image(
    file: Annotated[UploadFile, File(...)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    publisher: Annotated[RabbitMQPublisher, Depends(get_publisher)],
    storage: Annotated[StorageService, Depends(get_storage)],
) -> UploadAcceptedResponse:
    payload = await file.read()

    try:
        validate_upload_payload(
            filename=file.filename or "image.bin",
            content_type=file.content_type or "",
            payload=payload,
            max_size_bytes=settings.upload_max_size_bytes,
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        task = await create_inference_task(
            session=session,
            storage=storage,
            publisher=publisher,
            settings=settings,
            filename=file.filename or "image.bin",
            content_type=file.content_type or "application/octet-stream",
            payload=payload,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return UploadAcceptedResponse(task_id=task.id, status=task.status, s3_key=task.s3_key)

