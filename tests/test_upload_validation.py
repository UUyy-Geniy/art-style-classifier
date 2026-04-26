from __future__ import annotations

import pytest

from artstyle_backend.services.uploads import UploadValidationError, validate_upload_payload


def test_validate_upload_payload_accepts_valid_png() -> None:
    validate_upload_payload("test.png", "image/png", b"1234", max_size_bytes=10)


def test_validate_upload_payload_rejects_oversized_file() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload_payload("test.png", "image/png", b"12345678901", max_size_bytes=10)


def test_validate_upload_payload_rejects_unsupported_type() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload_payload("test.gif", "image/gif", b"1234", max_size_bytes=10)
