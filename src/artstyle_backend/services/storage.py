from __future__ import annotations

import asyncio
from functools import cached_property
from urllib.parse import urlparse

import boto3

from artstyle_backend.core.config import get_settings


class StorageService:
    def __init__(self, settings=None) -> None:
        self._settings = settings or get_settings()

    @cached_property
    def _client(self):
        session = boto3.session.Session()
        return session.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            region_name=self._settings.s3_region,
            aws_access_key_id=self._settings.s3_access_key,
            aws_secret_access_key=self._settings.s3_secret_key,
        )

    async def upload_bytes(self, key: str, payload: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._settings.s3_bucket_name,
            Key=key,
            Body=payload,
            ContentType=content_type,
        )

    async def download_bytes(self, key: str) -> bytes:
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self._settings.s3_bucket_name,
            Key=key,
        )
        return await asyncio.to_thread(response["Body"].read)

    def build_presigned_get_url(self, key: str) -> str | None:
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._settings.s3_bucket_name, "Key": key},
                ExpiresIn=self._settings.s3_presign_ttl_seconds,
            )
            if self._settings.s3_public_endpoint_url:
                internal = urlparse(self._settings.s3_endpoint_url)
                public = urlparse(self._settings.s3_public_endpoint_url)
                if internal.scheme and internal.netloc:
                    url = url.replace(f"{internal.scheme}://{internal.netloc}", f"{public.scheme}://{public.netloc}", 1)
            return url
        except Exception:
            return None
