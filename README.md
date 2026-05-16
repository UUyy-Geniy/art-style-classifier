# Art Style Classifier

Full local development stack for the Art Style Classifier project.

## Run Everything

```bash
docker compose up --build
```

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
