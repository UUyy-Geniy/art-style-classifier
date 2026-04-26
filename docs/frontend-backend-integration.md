# Frontend Integration Guide

Документ для фронтенда по интеграции с backend `Art Style Classifier`.

## Base URLs

Локально:

- API base URL: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

Все публичные API-ручки лежат под префиксом `/v1`.

## Общий сценарий работы

Основной flow для пользователя такой:

1. Пользователь выбирает изображение.
2. Фронтенд отправляет файл на `POST /v1/upload`.
3. Backend возвращает `task_id` и статус `queued`.
4. Фронтенд опрашивает `GET /v1/tasks/{task_id}`.
5. Когда статус становится `succeeded`, фронтенд вызывает `GET /v1/tasks/{task_id}/result`.
6. Фронтенд показывает top-1 стиль, top-k кандидатов и confidence.

В первой версии backend не отправляет realtime-события.  
Для ожидания результата используйте polling.

## Authentication

### Public user flow

Публичные user-ручки не требуют авторизации:

- `POST /v1/upload`
- `GET /v1/tasks/{task_id}`
- `GET /v1/tasks/{task_id}/result`

### Admin flow

Все admin-ручки требуют ровно один обязательный заголовок:

```http
X-Admin-Token: <your_admin_token>
```

Других способов авторизации для admin API сейчас нет.

## Endpoints

### 1. Upload image

`POST /v1/upload`

#### Request

- `Content-Type: multipart/form-data`
- поле формы: `file`

Поддерживаемые типы:

- `image/jpeg`
- `image/png`
- `image/webp`

Текущий лимит:

- `10 MB`

#### Example

```bash
curl -X POST \
  -F "file=@image.png;type=image/png" \
  http://localhost:8000/v1/upload
```

#### Response `202 Accepted`

```json
{
  "task_id": "d2eb54a9-d138-4113-ad32-bd874e71e5b8",
  "status": "queued",
  "s3_key": "uploads/2026/04/26/d2eb54a9-d138-4113-ad32-bd874e71e5b8/image.png"
}
```

#### Field meanings

- `task_id` — идентификатор асинхронной задачи; дальше по нему идет polling
- `status` — начальный статус задачи
- `s3_key` — внутренний путь до загруженного файла в object storage; фронту обычно нужен только для дебага

### 2. Poll task status

`GET /v1/tasks/{task_id}`

#### Example

```bash
curl http://localhost:8000/v1/tasks/d2eb54a9-d138-4113-ad32-bd874e71e5b8
```

#### Response

```json
{
  "task_id": "d2eb54a9-d138-4113-ad32-bd874e71e5b8",
  "status": "succeeded",
  "created_at": "2026-04-26T10:26:56.407123Z",
  "started_at": "2026-04-26T10:26:56.424631Z",
  "finished_at": "2026-04-26T10:26:56.600411Z",
  "error_message": null
}
```

#### Status values

- `queued` — задача создана и ждет worker
- `processing` — worker уже обрабатывает изображение
- `succeeded` — результат готов
- `failed` — задача завершилась ошибкой

#### Polling recommendation

- опрашивать раз в `1-2` секунды
- прекращать polling на `succeeded` или `failed`
- при `failed` показывать `error_message`

### 3. Get prediction result

`GET /v1/tasks/{task_id}/result`

Вызывать только после того, как статус задачи стал `succeeded`.

#### Response

```json
{
  "task_id": "d2eb54a9-d138-4113-ad32-bd874e71e5b8",
  "status": "succeeded",
  "image_s3_key": "uploads/2026/04/26/d2eb54a9-d138-4113-ad32-bd874e71e5b8/image.png",
  "image_url": "http://localhost:9000/artstyle-images/uploads/2026/04/26/d2eb54a9-d138-4113-ad32-bd874e71e5b8/image.png?...",
  "model_name": "art-style-classifier",
  "model_version": "stub-v1",
  "model_source": "internal_stub",
  "top_prediction": {
    "rank": 1,
    "confidence": 0.1939,
    "style": {
      "id": 2,
      "code": "expressionism",
      "name": "Expressionism",
      "description": "Эмоциональная деформация формы и интенсивная цветовая палитра."
    }
  },
  "top_k": [
    {
      "rank": 1,
      "confidence": 0.1939,
      "style": {
        "id": 2,
        "code": "expressionism",
        "name": "Expressionism",
        "description": "Эмоциональная деформация формы и интенсивная цветовая палитра."
      }
    }
  ],
  "completed_at": "2026-04-26T10:26:56.600411Z"
}
```

#### Field meanings

- `image_s3_key` — внутренний storage path исходного изображения
- `image_url` — presigned URL на исходный файл; можно использовать для предпросмотра
- `model_name` — имя модели в serving-контуре
- `model_version` — активная версия модели
- `model_source` — источник модели; сейчас это либо `internal_stub`, либо в будущем `mlflow`
- `top_prediction` — основной результат, который обычно показывается крупно
- `top_k` — полный список top-k кандидатов с confidence
- `style.code` — стабильный машинный код стиля
- `style.name` — отображаемое имя стиля
- `style.description` — краткое описание, которое можно показывать в UI

### 4. Get current active model

`GET /v1/admin/models/current`

#### Headers

```http
X-Admin-Token: change-me
```

#### Response

```json
{
  "model_name": "art-style-classifier",
  "model_version": "stub-v1",
  "model_source": "internal_stub",
  "revision": 1,
  "updated_at": "2026-04-26T10:24:44.000000Z"
}
```

#### Field meanings

- `revision` — служебный номер конфигурации serving-модели; растет при switch/reload

### 5. List available models

`GET /v1/admin/models/available`

#### Headers

```http
X-Admin-Token: change-me
```

#### Response

```json
[
  {
    "model_name": "art-style-classifier",
    "model_version": "stub-v1",
    "model_source": "internal_stub",
    "current_stage": "BuiltIn",
    "aliases": [],
    "is_active": true
  }
]
```

#### Field meanings

- `current_stage` — stage или служебная категория модели
- `aliases` — алиасы версии в MLflow, если используются
- `is_active` — выбрана ли эта модель в serving сейчас

### 6. Switch active model

`POST /v1/admin/models/switch`

#### Headers

```http
X-Admin-Token: change-me
Content-Type: application/json
```

#### Request body

```json
{
  "model_name": "art-style-classifier",
  "model_version": "stub-v1",
  "model_source": "internal_stub"
}
```

#### Field meanings

- `model_name` — логическое имя модели
- `model_version` — версия модели или alias
- `model_source` — `internal_stub` или `mlflow`

#### Response

```json
{
  "status": "ok",
  "model_name": "art-style-classifier",
  "model_version": "stub-v1",
  "model_source": "internal_stub",
  "revision": 2
}
```

### 7. Force worker reload

`POST /v1/admin/models/reload-workers`

#### Headers

```http
X-Admin-Token: change-me
```

#### Response

```json
{
  "status": "ok",
  "model_name": "art-style-classifier",
  "model_version": "stub-v1",
  "model_source": "internal_stub",
  "revision": 3
}
```

Использовать, если нужно принудительно поднять revision serving state.

### 8. Export retrain data

`POST /v1/admin/retrain/export`

#### Headers

```http
X-Admin-Token: change-me
```

#### Response

```json
{
  "export_id": 1,
  "export_key": "exports/retrain-export-20260426T102656Z.jsonl",
  "records_count": 12,
  "created_at": "2026-04-26T10:27:01.000000Z"
}
```

#### Field meanings

- `export_id` — id записи экспорта в backend DB
- `export_key` — путь до export-файла в S3-compatible storage
- `records_count` — сколько prediction records вошло в export

## Error handling

### Common status codes

- `400` — ошибка валидации запроса
- `401` — неверный `X-Admin-Token`
- `404` — задача или ресурс не найдены
- `409` — результат еще не готов
- `503` — backend временно не может поставить задачу в очередь или достучаться до зависимого сервиса

### Example validation error

```json
{
  "detail": "Unsupported content type 'image/gif'. Allowed: ['image/jpeg', 'image/png', 'image/webp']."
}
```

### Example not-ready result

```json
{
  "detail": "Prediction result is not ready yet."
}
```

## Frontend recommendations

### Upload UX

- проверяйте MIME type и file size на клиенте до отправки
- показывайте локальный preview до upload
- после успешного `upload` сразу сохраняйте `task_id` в state

### Polling UX

- интервал `1000-2000 ms`
- максимум ожидания определяйте на уровне UI
- при `failed` показывайте текст ошибки из `error_message`

### Result rendering

- `top_prediction` показывайте как основной стиль
- `top_k` используйте для таблицы или списка альтернатив
- `style.description` можно выводить как дополнительный explanatory text
- `confidence` фронт может форматировать в проценты, например `19.39%`

### Admin UI

- храните `X-Admin-Token` в отдельном admin-only client flow
- не смешивайте admin и public client instances
- для admin-запросов удобно сделать отдельный HTTP client с дефолтным заголовком `X-Admin-Token`

## Quick examples for frontend

### JavaScript upload

```javascript
const formData = new FormData();
formData.append("file", file);

const uploadResponse = await fetch("http://localhost:8000/v1/upload", {
  method: "POST",
  body: formData,
});

const uploadData = await uploadResponse.json();
```

### JavaScript polling

```javascript
async function waitForResult(taskId) {
  while (true) {
    const response = await fetch(`http://localhost:8000/v1/tasks/${taskId}`);
    const statusData = await response.json();

    if (statusData.status === "succeeded") {
      const resultResponse = await fetch(`http://localhost:8000/v1/tasks/${taskId}/result`);
      return resultResponse.json();
    }

    if (statusData.status === "failed") {
      throw new Error(statusData.error_message || "Inference failed");
    }

    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
}
```

### JavaScript admin request

```javascript
const response = await fetch("http://localhost:8000/v1/admin/models/current", {
  headers: {
    "X-Admin-Token": adminToken,
  },
});

const data = await response.json();
```
