# Art Style Classifier Backend

Локальный backend-стек для проекта распознавания художественных стилей:

- `FastAPI` API
- `RabbitMQ` для очереди inference-задач
- `PostgreSQL` для задач, предсказаний и служебных метаданных
- `MinIO + mc` как S3-совместимое object storage
- `MLflow` как model registry
- `Inference Worker` с deterministic stub и возможностью перейти на реальную MLflow-модель

`MLflow` использует отдельный `PostgreSQL` backend store (`postgres` database) и отдельный `psycopg2` SQLAlchemy dialect, чтобы не конфликтовать с `alembic_version` основного приложения и не упираться в несовместимость `MLflow` с `psycopg3` на запросах registry/experiments.

## Запуск полного dev-стека

Из корня репозитория:

```bash
cp .env.example .env
docker compose up --build
```

Проверить сервисы:

- Frontend: `http://localhost:5173`
- API: `http://localhost:8000/docs`
- Adminer: `http://localhost:8080`
- RabbitMQ UI: `http://localhost:15672`
- MinIO Console: `http://localhost:9001`
- MLflow: `http://localhost:5001`

Frontend в Docker работает через Vite dev server. Запросы UI к `/v1/*` проксируются на backend service `api:8000`, поэтому отдельная настройка `VITE_API_BASE_URL` для Docker-режима не нужна.

## Основные API

- `POST /v1/upload`
- `GET /v1/tasks/{task_id}`
- `GET /v1/tasks/{task_id}/result`
- `POST /v1/tasks/{task_id}/feedback`
- `GET /v1/admin/models/current`
- `GET /v1/admin/models/available`
- `POST /v1/admin/models/switch`
- `POST /v1/admin/models/reload-workers`
- `POST /v1/admin/retrain/export`
- `POST /v1/admin/retrain/run`

## Реальная модель

По умолчанию система стартует на `internal_stub`-модели, которая читает
`backend/src/artstyle_backend/ml_model/model_bundle/current_meta.json`.
После retrain с `--activate` достаточно перезапустить worker или вызвать
`POST /v1/admin/models/reload-workers`, чтобы backend перечитал активный bundle.

Базовый top-18 feature store для дообучения лежит рядом с bundle:

```text
backend/src/artstyle_backend/ml_model/model_bundle/features_large_cls_mean_top18_contemporary_merged_v1.npz
```

Этот `.npz` не хранится в Git: он весит больше лимита GitHub для обычного Git.
Новый разработчик должен получить его из внешнего хранилища.

Рекомендуемый bootstrap:

```bash
cp .env.example .env
# затем заполнить MODEL_FEATURE_STORE_URL в .env
docker compose --profile setup run --rm model-artifacts
docker compose up --build
```

Можно также положить файл вручную в `backend/src/artstyle_backend/ml_model/model_bundle/`.
Без этого файла inference работает, но feedback retrain не запустится.

## Feedback retrain

Сохранить исправление пользователя:

```bash
curl -X POST http://localhost:8000/v1/tasks/<task_id>/feedback \
  -H "Content-Type: application/json" \
  -d '{"correct_style_code":"Contemporary_Art"}'
```

Экспортировать approved feedback в CSV и локальные изображения:

```bash
curl -X POST http://localhost:8000/v1/admin/retrain/export \
  -H "X-Admin-Token: <ADMIN_TOKEN>"
```

В ответе создаётся запись `retrain_exports`; в `payload_preview.csv_path` будет путь к
`approved_feedback.csv` внутри `RETRAIN_FEEDBACK_EXPORT_DIR`.

Запуск retrain из backend-контейнера:

```bash
python /app/src/artstyle_backend/ml_model/retrain_from_feedback.py \
  --base-feature-store /app/src/artstyle_backend/ml_model/model_bundle/features_large_cls_mean_top18_contemporary_merged_v1.npz \
  --feedback-csv /app/data/retrain_feedback/<export_timestamp>/approved_feedback.csv \
  --model-bundle-dir /app/src/artstyle_backend/ml_model/model_bundle \
  --min-new-feedback 20 \
  --feedback-repeat 3 \
  --epochs 30 \
  --min-val-acc 0.60 \
  --activate
```

ML-команда также может зарегистрировать настоящую модель в `MLflow`, после чего admin API позволяет переключить active serving version без изменения backend-кода.

## Документация

- [Training Pipeline Contract](./docs/training-pipeline-contract.md)
- [Frontend Integration Guide](./docs/frontend-backend-integration.md)
- [Admin API Integration Guide](./docs/admin-api-integration.md)
