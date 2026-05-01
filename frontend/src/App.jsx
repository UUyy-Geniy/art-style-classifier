import { useEffect, useMemo, useState } from "react";
import { API_BASE_URL, getTaskResult, getTaskStatus, uploadImage } from "./api.js";
import "./App.css";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const POLLING_DELAY_MS = 1500;
const POLLING_TIMEOUT_MS = 120000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatFileSize(bytes) {
  if (!bytes) return "0 MB";
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function formatConfidence(value) {
  if (typeof value !== "number") return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function validateImage(file) {
  if (!file) return "Choose an image first.";

  if (!ALLOWED_TYPES.includes(file.type)) {
    return "Unsupported file type. Use JPG, PNG, or WEBP.";
  }

  if (file.size > MAX_FILE_SIZE) {
    return "File is too large. Maximum size is 10 MB.";
  }

  return "";
}

function StatusBadge({ status }) {
  if (!status) return null;

  return <span className={`status-badge status-${status}`}>{status}</span>;
}

function PredictionCard({ result }) {
  if (!result?.top_prediction) return null;

  const prediction = result.top_prediction;
  const style = prediction.style;

  return (
    <section className="card result-card">
      <div className="section-label">Top prediction</div>
      <div className="prediction-layout">
        <div>
          <h2>{style?.name || "Unknown style"}</h2>
          <p className="description">{style?.description || "No description provided."}</p>
          <div className="model-meta">
            <span>{result.model_name}</span>
            <span>{result.model_version}</span>
            <span>{result.model_source}</span>
          </div>
        </div>

        <div className="confidence-circle">
          <span>{formatConfidence(prediction.confidence)}</span>
          <small>confidence</small>
        </div>
      </div>
    </section>
  );
}

function TopKList({ items }) {
  if (!items?.length) return null;

  return (
    <section className="card">
      <div className="section-label">Alternative candidates</div>
      <div className="top-k-list">
        {items.map((item) => (
          <div className="candidate-row" key={`${item.rank}-${item.style?.code || item.style?.name}`}>
            <div className="candidate-main">
              <span className="rank">#{item.rank}</span>
              <div>
                <strong>{item.style?.name || "Unknown"}</strong>
                <p>{item.style?.description || "No description."}</p>
              </div>
            </div>
            <span className="candidate-confidence">{formatConfidence(item.confidence)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function App() {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [taskId, setTaskId] = useState("");
  const [status, setStatus] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const canSubmit = useMemo(() => Boolean(file) && !isLoading, [file, isLoading]);

  useEffect(() => {
    if (!file) {
      setPreviewUrl("");
      return;
    }

    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);

    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  function chooseFile(selectedFile) {
    setError("");
    setResult(null);
    setTaskId("");
    setStatus("");

    const validationError = validateImage(selectedFile);
    if (validationError) {
      setFile(null);
      setError(validationError);
      return;
    }

    setFile(selectedFile);
  }

  async function pollUntilDone(newTaskId) {
    const startedAt = Date.now();

    while (Date.now() - startedAt < POLLING_TIMEOUT_MS) {
      await sleep(POLLING_DELAY_MS);
      const statusData = await getTaskStatus(newTaskId);
      setStatus(statusData.status);

      if (statusData.status === "succeeded") {
        return statusData;
      }

      if (statusData.status === "failed") {
        throw new Error(statusData.error_message || "Image classification failed.");
      }
    }

    throw new Error("The request took too long. Try again or check the backend worker.");
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const validationError = validateImage(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsLoading(true);
    setError("");
    setResult(null);
    setStatus("uploading");

    try {
      const uploadData = await uploadImage(file);
      setTaskId(uploadData.task_id);
      setStatus(uploadData.status || "queued");

      await pollUntilDone(uploadData.task_id);
      const predictionResult = await getTaskResult(uploadData.task_id);

      setResult(predictionResult);
      setStatus(predictionResult.status || "succeeded");
    } catch (caughtError) {
      setError(caughtError.message || "Something went wrong.");
      setStatus("failed");
    } finally {
      setIsLoading(false);
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDragging(false);
    chooseFile(event.dataTransfer.files?.[0]);
  }

  function resetForm() {
    setFile(null);
    setPreviewUrl("");
    setTaskId("");
    setStatus("");
    setResult(null);
    setError("");
  }

  return (
    <main className="page-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">ML image recognition</p>
          <h1>Art Style Classifier</h1>
          <p className="hero-text">
            Upload an artwork image and get the predicted art style with confidence scores.
          </p>
        </div>
        <div className="api-pill">API: {API_BASE_URL}/v1</div>
      </section>

      <div className="grid-layout">
        <form className="card upload-card" onSubmit={handleSubmit}>
          <div className="section-label">Upload image</div>

          <label
            className={`dropzone ${isDragging ? "dropzone-active" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={isLoading}
              onChange={(event) => chooseFile(event.target.files?.[0])}
            />
            <span className="upload-icon">↑</span>
            <strong>Drop image here or click to choose</strong>
            <small>JPG, PNG, WEBP · max 10 MB</small>
          </label>

          {file && (
            <div className="file-info">
              <div>
                <strong>{file.name}</strong>
                <span>{file.type} · {formatFileSize(file.size)}</span>
              </div>
              <button className="ghost-button" type="button" onClick={resetForm} disabled={isLoading}>
                Clear
              </button>
            </div>
          )}

          <button className="primary-button" type="submit" disabled={!canSubmit}>
            {isLoading ? "Classifying..." : "Classify image"}
          </button>

          <div className="status-panel">
            <div>
              <span className="muted">Task ID</span>
              <strong>{taskId || "—"}</strong>
            </div>
            <div>
              <span className="muted">Status</span>
              <StatusBadge status={status || "idle"} />
            </div>
          </div>

          {error && <div className="error-box">{error}</div>}
        </form>

        <aside className="card preview-card">
          <div className="section-label">Preview</div>
          {previewUrl ? (
            <img src={previewUrl} alt="Selected artwork preview" />
          ) : (
            <div className="empty-preview">No image selected</div>
          )}
        </aside>
      </div>

      {isLoading && (
        <section className="card loading-card">
          <div className="spinner" />
          <div>
            <strong>Processing image</strong>
            <p>Current status: {status || "queued"}. The frontend is polling the backend.</p>
          </div>
        </section>
      )}

      {result && (
        <div className="results-stack">
          <PredictionCard result={result} />
          <TopKList items={result.top_k} />

          <section className="card details-card">
            <div className="section-label">Result details</div>
            <dl>
              <div>
                <dt>Completed at</dt>
                <dd>{formatDate(result.completed_at)}</dd>
              </div>
              <div>
                <dt>Image URL</dt>
                <dd>
                  {result.image_url ? (
                    <a href={result.image_url} target="_blank" rel="noreferrer">Open uploaded image</a>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div>
                <dt>Storage key</dt>
                <dd>{result.image_s3_key || "—"}</dd>
              </div>
            </dl>
          </section>
        </div>
      )}
    </main>
  );
}
