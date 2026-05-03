FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    HF_HUB_CACHE=/opt/huggingface/hub \
    TRANSFORMERS_CACHE=/opt/huggingface/transformers

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq-dev git \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md /app/
COPY backend/src /app/src
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic
COPY backend/docs /app/docs
COPY backend/scripts /app/scripts

RUN pip install --upgrade pip \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.5.1+cpu \
        torchvision==0.20.1+cpu \
    && pip install -e .[dev]

RUN python -c "from transformers import AutoImageProcessor, AutoModel; \
model_name='facebook/dinov2-large'; \
AutoImageProcessor.from_pretrained(model_name); \
AutoModel.from_pretrained(model_name); \
print('DINOv2-large downloaded and cached')"

COPY backend/tests /app/tests

CMD ["uvicorn", "artstyle_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]