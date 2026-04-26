from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from artstyle_backend.core.config import Settings, get_settings
from artstyle_backend.messaging.publisher import RabbitMQPublisher
from artstyle_backend.services.storage import StorageService


admin_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def get_app_settings() -> Settings:
    return get_settings()


def get_publisher(request: Request) -> RabbitMQPublisher:
    return request.app.state.publisher


def get_storage(request: Request) -> StorageService:
    return request.app.state.storage


def verify_admin_token(
    settings: Annotated[Settings, Depends(get_app_settings)],
    x_admin_token: Annotated[str | None, Security(admin_token_header)] = None,
) -> None:
    if x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token.",
        )
