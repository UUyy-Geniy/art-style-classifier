from __future__ import annotations

import os


os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://artstyle:artstyle@localhost:5432/artstyle"
)
os.environ.setdefault(
    "DATABASE_URL_SYNC", "postgresql+psycopg://artstyle:artstyle@localhost:5432/artstyle"
)
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")
os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

