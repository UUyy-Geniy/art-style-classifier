from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str
    database_url_sync: str

    rabbitmq_url: str
    rabbitmq_queue_name: str = "artstyle.inference"

    s3_endpoint_url: str
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: str
    s3_secret_key: str
    s3_bucket_name: str = "artstyle-images"
    s3_presign_ttl_seconds: int = 3600

    mlflow_tracking_uri: str
    mlflow_s3_bucket: str = "mlflow-artifacts"

    default_model_name: str = "art-style-classifier"
    default_model_version: str = "stub-v1"
    default_model_source: str = "internal_stub"

    admin_token: str = "change-me"
    upload_max_size_mb: int = 10
    default_top_k: int = 5
    log_level: str = "INFO"

    @property
    def upload_max_size_bytes(self) -> int:
        return self.upload_max_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
