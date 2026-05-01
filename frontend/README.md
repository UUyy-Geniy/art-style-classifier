# Art Style Classifier Frontend

React/Vite frontend for the public Art Style Classifier API.

## Run locally

### With Docker

From the repository root:

```bash
docker compose up --build
```

Open:

```text
http://localhost:5173
```

In Docker dev mode, frontend requests to `/v1/*` are proxied by Vite to the backend container. Keep `VITE_API_BASE_URL` empty unless you intentionally want to bypass the proxy.

### Without Docker

```bash
npm install
cp .env.example .env
npm run dev
```

Open the URL shown by Vite, usually:

```text
http://localhost:5173
```

The backend should be available at:

```text
http://localhost:8000
```

You can change the backend URL in `.env`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## What this frontend does

1. Validates the selected image on the client.
2. Shows a local preview before upload.
3. Sends the image to `POST /v1/upload` as `multipart/form-data`.
4. Polls `GET /v1/tasks/{task_id}` every 1.5 seconds.
5. Calls `GET /v1/tasks/{task_id}/result` only after the task succeeds.
6. Shows the main prediction, confidence, style description, model info, and top-k alternatives.

## Notes

- Supported image types: JPG, PNG, WEBP.
- Max file size: 10 MB.
- If you get a CORS error, the backend must allow requests from the Vite dev server origin, for example `http://localhost:5173`.
- Admin endpoints are intentionally not mixed into the public user flow.
