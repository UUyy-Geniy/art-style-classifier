# Art Style Classifier

Full local development stack for the Art Style Classifier project.

## Run Everything

First copy local environment defaults:

```bash
cp .env.example .env
```

The app can start without the large retrain feature store, but feedback retraining needs:

```text
backend/src/artstyle_backend/ml_model/model_bundle/features_large_cls_mean_top18_contemporary_merged_v1.npz
```

This file is intentionally not stored in Git because it is about 632 MB. Put it in one of these places:

- GitHub Release asset
- S3 or MinIO object
- HuggingFace dataset/model file
- shared internal storage with a direct download URL

Then set `MODEL_FEATURE_STORE_URL` in `.env` and download it:

```bash
docker compose --profile setup run --rm model-artifacts
```

Alternatively, if you have the file locally, copy it directly into:

```text
backend/src/artstyle_backend/ml_model/model_bundle/
```

or run:

```bash
MODEL_FEATURE_STORE_URL="https://example.com/features_large_cls_mean_top18_contemporary_merged_v1.npz" \
  ./scripts/download-model-artifacts.sh
```

After that start the stack:

```bash
docker compose up --build
```

On the first real inference/retrain run, the worker/API may download `facebook/dinov2-large`
from HuggingFace. That happens at runtime and is cached in the Docker volume
`huggingface_cache`, so later restarts reuse it. If you want to bake DINOv2 into the image
instead, set `PRELOAD_DINOV2=1` in `.env`, but the initial Docker build will be much slower.

Docker Compose project name is fixed as `art-style-classifier`, so Docker Desktop/OrbStack groups the stack under that name instead of deriving it from the repository folder.

Main URLs:

- Frontend: `http://localhost:5173`
- Backend Swagger: `http://localhost:8000/docs`
- Adminer: `http://localhost:8080`
- RabbitMQ UI: `http://localhost:15672`
- MinIO Console: `http://localhost:9001`
- MLflow: `http://localhost:5001`

The default frontend mode is Vite dev server with hot reload. Browser requests from the frontend to `/v1/*` are proxied by Vite to the backend container at `http://api:8000`, so the UI does not need to call `localhost:8000` directly.

## Configuration

The compose file has safe local defaults. Optional overrides can be placed in a root `.env` file.

Useful variables:

- `VITE_API_BASE_URL`: leave empty for Docker dev mode so Vite proxy handles `/v1`; set to `http://localhost:8000` only when running the frontend outside Docker.
- `CORS_ALLOWED_ORIGINS`: comma-separated browser origins allowed by the backend, defaulting to `http://localhost:5173,http://127.0.0.1:5173`.
- `ADMIN_TOKEN`: token required by `/v1/admin/*`, defaulting to `change-me`.
- `MODEL_FEATURE_STORE_URL`: optional direct download URL for the large `.npz` used by feedback retraining.
- `MODEL_FEATURE_STORE_SHA256`: optional checksum for verifying the downloaded `.npz`.
- `PRELOAD_DINOV2`: default `0`. Set to `1` only when you want Docker build to preload DINOv2 into the image.
- `HF_TOKEN`: optional HuggingFace token for higher rate limits during the first DINOv2 download.

If frontend dependencies change and Docker keeps an old `node_modules` volume, recreate it:

```bash
docker compose down -v
docker compose up --build
```

## Smoke Check

1. Open `http://localhost:5173`.
2. Upload a JPG, PNG, or WEBP image up to 10 MB.
3. Wait for the task status to become `succeeded`.
4. Confirm that the top prediction and top-k candidates are displayed.

Backend-only API flow:

```bash
curl http://localhost:8000/docs
```

## Development Notes

- Backend code lives in `backend/`; its image is built from `docker/backend.Dockerfile`.
- Frontend code lives in `frontend/`; its dev image is built from `docker/frontend.dev.Dockerfile`.
- The default model source is `internal_stub`, so the stack can classify images without a registered external MLflow model.
- Feedback retraining requires the `.npz` feature store artifact. Inference uses the tracked `current_meta.json`, head `.pt`, and label encoder files.
