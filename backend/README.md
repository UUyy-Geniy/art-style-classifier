# Art Style Classifier Backend

Локальный backend-стек для проекта распознавания художественных стилей:

- `FastAPI` API
- `RabbitMQ` для очереди inference-задач
- `PostgreSQL` для задач, предсказаний и служебных метаданных
- `MinIO + mc` как S3-совместимое object storage
- `MLflow` как model registry
- `Inference Worker` с deterministic stub и возможностью перейти на реальную MLflow-модель

`MLflow` использует отдельный `PostgreSQL` backend store (`postgres` database) и отдельный `psycopg2` SQLAlchemy dialect, чтобы не конфликтовать с `alembic_version` основного приложения и не упираться в несовместимость `MLflow` с `psycopg3` на запросах registry/experiments.

## Запуск локально

1. Создать `.env` из [.env.example](./.env.example).
2. Поднять стек:

```bash
docker compose up --build
```

3. Проверить сервисы:

- API: `http://localhost:8000/docs`
- Adminer: `http://localhost:8080`
- RabbitMQ UI: `http://localhost:15672`
- MinIO Console: `http://localhost:9001`
- MLflow: `http://localhost:5001`

## Основные API

- `POST /v1/upload`
- `GET /v1/tasks/{task_id}`
- `GET /v1/tasks/{task_id}/result`
- `GET /v1/admin/models/current`
- `GET /v1/admin/models/available`
- `POST /v1/admin/models/switch`
- `POST /v1/admin/models/reload-workers`
- `POST /v1/admin/retrain/export`

## Реальная модель

По умолчанию система стартует на `internal_stub`-модели.  
ML-команда может зарегистрировать настоящую модель в `MLflow`, после чего admin API позволяет переключить active serving version без изменения backend-кода.

## Документация

- [Training Pipeline Contract](./docs/training-pipeline-contract.md)
- [Frontend Integration Guide](./docs/frontend-backend-integration.md)
