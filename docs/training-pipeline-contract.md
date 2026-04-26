# Training Pipeline Contract for Art Style Classifier

## Purpose

Этот документ фиксирует интеграционный контракт между backend-командой и ML-командой.  
Цель: сделать так, чтобы новая версия модели подключалась к `Inference Worker` без ручной адаптации backend-кода.

## Serving Contract

### Input

Worker передает модели:

- `image_bytes`: исходные байты изображения
- `top_k`: сколько кандидатов нужно вернуть

Если модель обернута как `MLflow pyfunc`, она должна принимать payload, из которого можно восстановить эти два поля без дополнительной бизнес-логики в backend.

### Output

Модель обязана вернуть `top_k` кандидатов в формате:

```json
[
  {
    "style_code": "impressionism",
    "confidence": 0.73,
    "rank": 1
  }
]
```

Требования:

- `confidence` нормализован в диапазон `0..1`
- `rank` начинается с `1`
- `style_code` совпадает со справочником `styles` в backend
- структура ответа не меняется между версиями без нового интеграционного контракта

## Model Artifact Requirements

- Модель должна публиковаться в `MLflow`
- Каждая публикация создает новую версию, а не перезаписывает старую
- Worker должен уметь загрузить artifact без ручных шагов
- В артефакте нужен воспроизводимый dependency contract: `requirements.txt`, `conda.yaml` или эквивалент
- В метаданных модели должны быть:
  - `model_name`
  - `model_version`
  - список поддерживаемых `style_code`
  - формат входного payload
  - рекомендуемый `top_k`
  - описание preprocessing, если он встроен в artifact

## Training Pipeline Requirements

- Training и serving разделены
- Обучение не запускается из backend API
- Backend отдает export с `s3_key + prediction metadata + future feedback`
- Training pipeline должен потреблять этот export без ручной правки формата
- Для каждой модели ML-команда хранит:
  - `dataset snapshot`
  - `training code version`
  - `hyperparameters`
  - `evaluation metrics`
  - `artifact URI`

## Promotion Flow

- Production artifact не перезаписывается
- Новая модель публикуется как новая версия в `MLflow`
- Переключение serving-версии происходит через backend admin API
- Перед promotion ML-команда прикладывает краткий evaluation report

Минимум в evaluation report:

- метрики на holdout-наборе
- список поддерживаемых классов
- время cold load
- средняя latency на inference
- описание ограничений модели

## Acceptance Criteria for ML Team

- Модель загружается worker-ом в чистом локальном окружении
- Результат inference детерминирован для одной и той же версии модели
- Все `style_code` валидны относительно backend dictionary
- Есть smoke-набор изображений для интеграционной проверки
- Preprocessing инкапсулирован внутри model artifact, а не дублируется в backend

## Recommendations

- Делать label space фиксированным и версионируемым
- Не хранить пользовательские описания стилей внутри модели
- При изменении contract payload публиковать новую совместимую версию integration spec
- До подключения production-модели сначала прогонять локальный smoke через MLflow и worker

