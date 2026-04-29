from __future__ import annotations


class UploadValidationError(ValueError):
    pass


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_upload_payload(
    filename: str,
    content_type: str,
    payload: bytes,
    max_size_bytes: int,
) -> None:
    if not filename:
        raise UploadValidationError("Filename is required.")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadValidationError(
            f"Unsupported content type '{content_type}'. Allowed: {sorted(ALLOWED_CONTENT_TYPES)}."
        )
    if not payload:
        raise UploadValidationError("Uploaded file is empty.")
    if len(payload) > max_size_bytes:
        raise UploadValidationError(f"Uploaded file exceeds limit of {max_size_bytes} bytes.")

