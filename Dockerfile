FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY docs /app/docs
COPY scripts /app/scripts

RUN pip install --upgrade pip \
    && pip install -e .

CMD ["uvicorn", "artstyle_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

