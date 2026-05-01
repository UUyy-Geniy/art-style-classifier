from __future__ import annotations

import pytest
from fastapi import HTTPException

from artstyle_backend.api.deps import verify_admin_token
from artstyle_backend.core.config import get_settings


def test_verify_admin_token_accepts_valid_header() -> None:
    settings = get_settings()
    verify_admin_token(settings, x_admin_token=settings.admin_token)


def test_verify_admin_token_rejects_invalid_header() -> None:
    settings = get_settings()
    with pytest.raises(HTTPException):
        verify_admin_token(settings, x_admin_token="wrong-token")
