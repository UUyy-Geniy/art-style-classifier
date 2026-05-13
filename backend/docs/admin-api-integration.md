# Admin API Integration Guide

Документ для frontend-команды по верстке админки и подключению admin API.

## Base URLs

Локально:

- API base URL: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

В Docker dev mode frontend может ходить в относительные URL, потому что Vite proxy прокидывает `/v1/*` на backend:

```text
/v1/admin/...
```

При запуске frontend вне Docker используйте `VITE_API_BASE_URL=http://localhost:8000`.

## Авторизация

Все admin-ручки требуют заголовок:

```http
X-Admin-Token: <ADMIN_TOKEN>
```

Токен берется из backend env `ADMIN_TOKEN`. По умолчанию в dev окружении используется `change-me`, но фронт не должен хардкодить это значение.

Если токен отсутствует или неверный, backend отвечает:

```http
401 Unauthorized
```

```json
{
  "detail": "Invalid admin token."
}
```

Рекомендация для frontend:

- сделать отдельный admin HTTP client
- не смешивать public API client и admin API client
- хранить token только в admin-only flow
- на `401` сбрасывать локальное состояние админки и показывать форму ввода токена

## Что должна уметь первая версия админки

Минимальный admin UI можно собрать из трех блоков:

1. Текущая serving-модель.
2. Список доступных моделей и действие "переключить".
3. Сервисные действия: reload workers и export retrain dataset.

Важно: в текущем backend нет отдельных admin-ручек для просмотра пользователей, просмотра всех задач, модерации feedback или скачивания export-файла по URL. Админка должна опираться только на ручки ниже, пока backend не расширит контракт.

## Endpoints

### 1. Получить текущую активную модель

```http
GET /v1/admin/models/current
```

#### Headers

```http
X-Admin-Token: <ADMIN_TOKEN>
```

#### Response `200 OK`

```json
{
  "model_name": "art-style-classifier",
  "model_version": "stub-v1",
  "model_source": "internal_stub",
  "revision": 1,
  "updated_at": "2026-04-26T10:24:44.000000Z"
}
```

#### Поля

- `model_name` — логическое имя модели в serving-контуре.
- `model_version` — активная версия модели или MLflow alias.
- `model_source` — источник модели: `internal_stub` или `mlflow`.
- `revision` — служебный номер serving-конфигурации. Растет после switch/reload.
- `updated_at` — когда serving state был обновлен.

#### UI

Показывайте как read-only summary: имя, версия, источник, revision и время обновления.

### 2. Получить список доступных моделей

```http
GET /v1/admin/models/available
```

#### Headers

```http
X-Admin-Token: <ADMIN_TOKEN>
```

#### Response `200 OK`

```json
[
  {
    "model_name": "art-style-classifier",
    "model_version": "stub-v1",
    "model_source": "internal_stub",
    "current_stage": "BuiltIn",
    "aliases": [],
    "is_active": true
  },
  {
    "model_name": "art-style-classifier",
    "model_version": "12",
    "model_source": "mlflow",
    "current_stage": "None",
    "aliases": ["champion"],
    "is_active": false
  }
]
```

#### Поля

- `model_name` — логическое имя модели.
- `model_version` — версия модели. Для MLflow это может быть числовая версия.
- `model_source` — `internal_stub` или `mlflow`.
- `current_stage` — stage/категория модели. Для встроенной stub-модели приходит `BuiltIn`.
- `aliases` — список MLflow aliases, если они есть.
- `is_active` — выбрана ли модель сейчас в serving.

#### UI

Подойдет таблица:

- Model
- Version
- Source
- Stage
- Aliases
- Status
- Action

Для строки с `is_active: true` действие switch нужно отключить или заменить на read-only badge `Active`.

### 3. Переключить активную модель

```http
POST /v1/admin/models/switch
```

#### Headers

```http
X-Admin-Token: <ADMIN_TOKEN>
Content-Type: application/json
```

#### Request body

```json
{
  "model_name": "art-style-classifier",
  "model_version": "12",
  "model_source": "mlflow"
}
```

Для возврата на встроенную dev-модель:

```json
{
  "model_name": "art-style-classifier",
  "model_version": "stub-v1",
  "model_source": "internal_stub"
}
```

#### Поля request body

- `model_name` — опционально, но frontend лучше всегда отправлять значение из выбранной строки.
- `model_version` — обязательно.
- `model_source` — опционально, default на backend: `mlflow`. Frontend лучше всегда отправлять явно.

Допустимые `model_source`:

- `internal_stub`
- `mlflow`

#### Response `200 OK`

```json
{
  "status": "ok",
  "model_name": "art-style-classifier",
  "model_version": "12",
  "model_source": "mlflow",
  "revision": 2
}
```

#### Ошибки

Если MLflow version/alias недоступен:

```http
400 Bad Request
```

```json
{
  "detail": "MLflow model 'art-style-classifier' with version or alias '12' is not available."
}
```

Если `model_source` не входит в enum, FastAPI вернет validation error `422 Unprocessable Entity`.

#### UI

Перед switch лучше показать confirmation dialog с выбранной моделью. После успешного switch нужно заново запросить:

- `GET /v1/admin/models/current`
- `GET /v1/admin/models/available`

### 4. Принудительно обновить revision для workers

```http
POST /v1/admin/models/reload-workers
```

#### Headers

```http
X-Admin-Token: <ADMIN_TOKEN>
```

#### Request body

Тела запроса нет.

#### Response `200 OK`

```json
{
  "status": "ok",
  "model_name": "art-style-classifier",
  "model_version": "stub-v1",
  "model_source": "internal_stub",
  "revision": 3
}
```

#### UI

Это сервисная кнопка `Reload workers`. Используйте ее после обновления model bundle или когда нужно принудительно поднять `revision`, чтобы serving перечитал активную конфигурацию.

После успеха обновите блок текущей модели через `GET /v1/admin/models/current`.

### 5. Экспортировать approved feedback для retrain

```http
POST /v1/admin/retrain/export
```

#### Headers

```http
X-Admin-Token: <ADMIN_TOKEN>
```

#### Request body

Тела запроса нет.

#### Response `200 OK`

```json
{
  "export_id": 1,
  "export_key": "exports/retrain-feedback-20260426T102656Z.jsonl",
  "records_count": 12,
  "payload_preview": {
    "csv_path": "/app/data/retrain_feedback/20260426T102656Z/approved_feedback.csv",
    "images_dir": "/app/data/retrain_feedback/20260426T102656Z/images",
    "rows": [
      {
        "feedback_id": 1,
        "image_path": "/app/data/retrain_feedback/20260426T102656Z/images/1_image.png",
        "correct_style_code": "Contemporary_Art",
        "predicted_style_code": "Impressionism",
        "model_version": "stub-v1",
        "created_at": "2026-04-26T10:20:00+00:00",
        "task_id": "d2eb54a9-d138-4113-ad32-bd874e71e5b8",
        "s3_key": "uploads/2026/04/26/d2eb54a9-d138-4113-ad32-bd874e71e5b8/image.png",
        "model_name": "art-style-classifier",
        "model_source": "internal_stub",
        "top_confidence": 0.73,
        "candidates": [
          {
            "style_code": "Impressionism",
            "confidence": 0.73,
            "rank": 1
          }
        ]
      }
    ]
  },
  "created_at": "2026-04-26T10:27:01.000000Z"
}
```

#### Поля

- `export_id` — id записи экспорта в backend DB.
- `export_key` — путь до JSONL export-файла в S3-compatible storage.
- `records_count` — сколько approved feedback записей попало в export.
- `payload_preview` — preview для админки и ML-команды. Может быть `null`, но обычно содержит `csv_path`, `images_dir` и первые строки `rows`.
- `created_at` — время создания export-записи.

#### UI

Показывайте результат последнего запуска:

- export id
- records count
- export key
- csv path из `payload_preview.csv_path`, если есть
- images dir из `payload_preview.images_dir`, если есть

Если `records_count: 0`, это не ошибка. Это означает, что backend не нашел approved feedback записей, подходящих под текущий export-фильтр.

Текущая реализация export не помечает feedback как использованный в обучении. Если backend не будет отдельно обновлять `used_in_training`, повторный export может вернуть те же записи.

## Общая обработка ошибок

Backend возвращает стандартный FastAPI JSON:

```json
{
  "detail": "Human readable error"
}
```

Для validation errors `detail` будет массивом:

```json
{
  "detail": [
    {
      "type": "enum",
      "loc": ["body", "model_source"],
      "msg": "Input should be 'internal_stub' or 'mlflow'",
      "input": "wrong"
    }
  ]
}
```

Рекомендуемая frontend-логика:

- если `detail` строка, показывать ее как текст ошибки
- если `detail` массив, склеить `msg` из элементов массива
- если тело не JSON, показывать `Request failed with status <status>`

## Пример admin client

```javascript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const ADMIN_PREFIX = "/v1/admin";

function getErrorMessage(data, status) {
  if (data && typeof data === "object") {
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    }
  }

  if (typeof data === "string" && data.trim()) return data;
  return `Request failed with status ${status}`;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response.status));
  }

  return data;
}

async function adminRequest(path, adminToken, options = {}) {
  const response = await fetch(`${API_BASE_URL}${ADMIN_PREFIX}${path}`, {
    ...options,
    headers: {
      "X-Admin-Token": adminToken,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  return parseResponse(response);
}

export function getCurrentModel(adminToken) {
  return adminRequest("/models/current", adminToken);
}

export function getAvailableModels(adminToken) {
  return adminRequest("/models/available", adminToken);
}

export function switchModel(adminToken, model) {
  return adminRequest("/models/switch", adminToken, {
    method: "POST",
    body: JSON.stringify({
      model_name: model.model_name,
      model_version: model.model_version,
      model_source: model.model_source,
    }),
  });
}

export function reloadWorkers(adminToken) {
  return adminRequest("/models/reload-workers", adminToken, {
    method: "POST",
  });
}

export function exportRetrainDataset(adminToken) {
  return adminRequest("/retrain/export", adminToken, {
    method: "POST",
  });
}
```

## Рекомендуемый layout админки

### Верхняя панель

- поле/token input или состояние `Admin authenticated`
- кнопка refresh
- inline error area

### Блок Current model

- `model_name`
- `model_version`
- `model_source`
- `revision`
- `updated_at`

### Блок Available models

Таблица моделей с кнопкой switch. Для активной модели показывать badge `Active`.

### Блок Service actions

- `Reload workers`
- `Export retrain dataset`

После каждого успешного действия показывать toast/status message и обновлять связанные данные.

## Refresh strategy

При открытии админки:

1. Запросить `GET /v1/admin/models/current`.
2. Запросить `GET /v1/admin/models/available`.

После `switch`:

1. Обновить current model.
2. Обновить available models.

После `reload-workers`:

1. Обновить current model.

После `retrain/export`:

1. Показать response в service actions.
2. Current model обновлять не нужно.
