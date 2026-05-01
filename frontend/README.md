# Art Style Classifier Frontend

React/Vite frontend for the public Art Style Classifier API.

## Run locally

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
