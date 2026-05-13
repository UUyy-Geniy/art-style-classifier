import { useEffect, useMemo, useState } from "react";
import {
  API_BASE_URL,
  exportRetrainFeedback,
  getAvailableModels,
  getCurrentModel,
  getRetrainJob,
  getTaskResult,
  getTaskStatus,
  listRetrainJobs,
  reloadWorkers,
  runRetrain,
  submitPredictionFeedback,
  switchModel,
  uploadImage,
} from "./api.js";
import "./App.css";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_FILE_SIZE = 10 * 1024 * 1024;
const POLLING_DELAY_MS = 1500;
const POLLING_TIMEOUT_MS = 120000;
const RETRAIN_POLLING_DELAY_MS = 2000;
const STYLE_OPTIONS = [
  { code: "Abstract_Expressionism", name: "Abstract Expressionism" },
  { code: "Art_Nouveau", name: "Art Nouveau" },
  { code: "Baroque", name: "Baroque" },
  { code: "Contemporary_Art", name: "Contemporary Art" },
  { code: "Cubism", name: "Cubism" },
  { code: "Early_Renaissance", name: "Early Renaissance" },
  { code: "Expressionism", name: "Expressionism" },
  { code: "High_Renaissance", name: "High Renaissance" },
  { code: "Impressionism", name: "Impressionism" },
  { code: "Mannerism_Late_Renaissance", name: "Mannerism / Late Renaissance" },
  { code: "Naive_Art_Primitivism", name: "Naive Art / Primitivism" },
  { code: "Northern_Renaissance", name: "Northern Renaissance" },
  { code: "Post_Impressionism", name: "Post-Impressionism" },
  { code: "Realism", name: "Realism" },
  { code: "Rococo", name: "Rococo" },
  { code: "Romanticism", name: "Romanticism" },
  { code: "Symbolism", name: "Symbolism" },
  { code: "Ukiyo_e", name: "Ukiyo-e" },
];

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

function FeedbackPanel({
  result,
  selectedStyleCode,
  feedbackStatus,
  feedbackError,
  isSubmittingFeedback,
  onSelectedStyleCodeChange,
  onSubmitFeedback,
}) {
  if (!result?.task_id) return null;

  return (
    <section className="card feedback-card">
      <div>
        <div className="section-label">Correction</div>
        <h3>Submit correct style</h3>
        <p>
          If the prediction is wrong, choose the correct production style code and save it for the
          next feedback retrain export.
        </p>
      </div>

      <form className="feedback-form" onSubmit={onSubmitFeedback}>
        <label htmlFor="correct-style">Correct style</label>
        <div className="feedback-controls">
          <select
            id="correct-style"
            value={selectedStyleCode}
            disabled={isSubmittingFeedback}
            onChange={(event) => onSelectedStyleCodeChange(event.target.value)}
          >
            {STYLE_OPTIONS.map((style) => (
              <option value={style.code} key={style.code}>
                {style.name} ({style.code})
              </option>
            ))}
          </select>
          <button className="primary-button" type="submit" disabled={isSubmittingFeedback}>
            {isSubmittingFeedback ? "Saving..." : "Save correction"}
          </button>
        </div>
      </form>

      {feedbackStatus && <div className="success-box">{feedbackStatus}</div>}
      {feedbackError && <div className="error-box">{feedbackError}</div>}
    </section>
  );
}

function AdminPanel({
  adminToken,
  adminResult,
  adminError,
  isAdminLoading,
  switchForm,
  retrainForm,
  onAdminTokenChange,
  onLoadCurrentModel,
  onLoadAvailableModels,
  onReloadWorkers,
  onExportRetrainFeedback,
  onListRetrainJobs,
  onSwitchFormChange,
  onSwitchModel,
  onRetrainFormChange,
  onRunRetrain,
}) {
  return (
    <main className="page-shell admin-page">
      <section className="admin-hero">
        <div>
          <div className="section-label">Admin</div>
          <h1>Operations Console</h1>
          <p className="hero-text">
            Manage serving state, inspect available model registry entries, reload workers, and
            export approved feedback for retraining.
          </p>
        </div>
        <nav className="admin-nav" aria-label="Admin navigation">
          <a href="/">Classifier</a>
          <span>/v1/admin</span>
        </nav>
      </section>

      <div className="admin-layout">
        <section className="card admin-card">
          <div className="admin-card-heading">
            <div>
              <div className="section-label">Auth</div>
              <h2>Access</h2>
            </div>
            <span className="admin-endpoint">X-Admin-Token</span>
          </div>

          <label className="admin-token-field" htmlFor="admin-token">
            <span>Admin token</span>
            <input
              id="admin-token"
              type="password"
              autoComplete="off"
              value={adminToken}
              placeholder="change-me"
              onChange={(event) => onAdminTokenChange(event.target.value)}
            />
          </label>
        </section>

        <section className="card admin-card">
          <div className="admin-card-heading">
            <div>
              <div className="section-label">Serving</div>
              <h2>Model state</h2>
            </div>
            <span className="admin-endpoint">models</span>
          </div>

          <div className="admin-actions">
            <button className="ghost-button" type="button" disabled={isAdminLoading} onClick={onLoadCurrentModel}>
              Current model
            </button>
            <button className="ghost-button" type="button" disabled={isAdminLoading} onClick={onLoadAvailableModels}>
              Available models
            </button>
            <button className="primary-button" type="button" disabled={isAdminLoading} onClick={onReloadWorkers}>
              Reload workers
            </button>
          </div>
        </section>

        <section className="card admin-card">
          <div className="admin-card-heading">
            <div>
              <div className="section-label">Switch</div>
              <h2>Activate model</h2>
            </div>
            <span className="admin-endpoint">models/switch</span>
          </div>

          <form className="admin-form" onSubmit={onSwitchModel}>
            <label>
              <span>Model source</span>
              <select
                value={switchForm.model_source}
                onChange={(event) => onSwitchFormChange("model_source", event.target.value)}
              >
                <option value="internal_stub">internal_stub</option>
                <option value="mlflow">mlflow</option>
              </select>
            </label>

            <label>
              <span>Model name</span>
              <input
                value={switchForm.model_name}
                placeholder="art-style-classifier"
                onChange={(event) => onSwitchFormChange("model_name", event.target.value)}
              />
            </label>

            <label>
              <span>Model version</span>
              <input
                value={switchForm.model_version}
                placeholder="stub-v1"
                onChange={(event) => onSwitchFormChange("model_version", event.target.value)}
              />
            </label>

            <button className="primary-button" type="submit" disabled={isAdminLoading}>
              Switch model
            </button>
          </form>
        </section>

        <section className="card admin-card">
          <div className="admin-card-heading">
            <div>
              <div className="section-label">Retrain</div>
              <h2>Feedback export</h2>
            </div>
            <span className="admin-endpoint">retrain/export</span>
          </div>

          <div className="admin-actions">
            <button className="primary-button" type="button" disabled={isAdminLoading} onClick={onExportRetrainFeedback}>
              Export feedback CSV
            </button>
            <button className="ghost-button" type="button" disabled={isAdminLoading} onClick={onListRetrainJobs}>
              Retrain jobs
            </button>
          </div>
        </section>

        <section className="card admin-card admin-card-wide">
          <div className="admin-card-heading">
            <div>
              <div className="section-label">Training</div>
              <h2>Run retrain</h2>
            </div>
            <span className="admin-endpoint">retrain/run</span>
          </div>

          <form className="admin-form admin-form-grid" onSubmit={onRunRetrain}>
            <label className="admin-field-wide">
              <span>Feedback CSV path</span>
              <input
                value={retrainForm.feedback_csv}
                required
                placeholder="/app/data/retrain_feedback/<timestamp>/approved_feedback.csv"
                onChange={(event) => onRetrainFormChange("feedback_csv", event.target.value)}
              />
            </label>

            <label>
              <span>Min feedback</span>
              <input
                type="number"
                min="1"
                value={retrainForm.min_new_feedback}
                onChange={(event) => onRetrainFormChange("min_new_feedback", event.target.value)}
              />
            </label>

            <label>
              <span>Feedback repeat</span>
              <input
                type="number"
                min="1"
                value={retrainForm.feedback_repeat}
                onChange={(event) => onRetrainFormChange("feedback_repeat", event.target.value)}
              />
            </label>

            <label>
              <span>Epochs</span>
              <input
                type="number"
                min="1"
                value={retrainForm.epochs}
                onChange={(event) => onRetrainFormChange("epochs", event.target.value)}
              />
            </label>

            <label>
              <span>Batch size</span>
              <input
                type="number"
                min="1"
                value={retrainForm.batch_size}
                onChange={(event) => onRetrainFormChange("batch_size", event.target.value)}
              />
            </label>

            <label>
              <span>Min val accuracy</span>
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={retrainForm.min_val_acc}
                onChange={(event) => onRetrainFormChange("min_val_acc", event.target.value)}
              />
            </label>

            <label>
              <span>Device</span>
              <select
                value={retrainForm.device}
                onChange={(event) => onRetrainFormChange("device", event.target.value)}
              >
                <option value="auto">auto</option>
                <option value="cpu">cpu</option>
                <option value="cuda">cuda</option>
              </select>
            </label>

            <label className="admin-checkbox">
              <input
                type="checkbox"
                checked={retrainForm.activate}
                onChange={(event) => onRetrainFormChange("activate", event.target.checked)}
              />
              <span>Activate if validation passes</span>
            </label>

            <button className="primary-button admin-field-wide" type="submit" disabled={isAdminLoading}>
              {isAdminLoading ? "Running..." : "Run retrain"}
            </button>
          </form>
        </section>
      </div>

      {adminError && <div className="error-box admin-message">{adminError}</div>}

      {adminResult && (
        <section className="admin-result">
          <div className="admin-result-title">{adminResult.title}</div>
          <pre>{JSON.stringify(adminResult.data, null, 2)}</pre>
        </section>
      )}
    </main>
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
  const [selectedStyleCode, setSelectedStyleCode] = useState("Contemporary_Art");
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [feedbackError, setFeedbackError] = useState("");
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [adminToken, setAdminToken] = useState(() => localStorage.getItem("artstyleAdminToken") || "");
  const [adminResult, setAdminResult] = useState(null);
  const [adminError, setAdminError] = useState("");
  const [isAdminLoading, setIsAdminLoading] = useState(false);
  const [switchForm, setSwitchForm] = useState({
    model_source: "internal_stub",
    model_name: "art-style-classifier",
    model_version: "stub-v1",
  });
  const [retrainForm, setRetrainForm] = useState({
    feedback_csv: localStorage.getItem("artstyleRetrainFeedbackCsv") || "",
    min_new_feedback: "20",
    feedback_repeat: "3",
    epochs: "30",
    batch_size: "256",
    min_val_acc: "0.60",
    device: "auto",
    activate: false,
  });

  const canSubmit = useMemo(() => Boolean(file) && !isLoading, [file, isLoading]);
  const isAdminRoute = window.location.pathname === "/admin";

  useEffect(() => {
    if (!file) {
      setPreviewUrl("");
      return;
    }

    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);

    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  useEffect(() => {
    if (adminToken) {
      localStorage.setItem("artstyleAdminToken", adminToken);
    } else {
      localStorage.removeItem("artstyleAdminToken");
    }
  }, [adminToken]);

  useEffect(() => {
    if (retrainForm.feedback_csv) {
      localStorage.setItem("artstyleRetrainFeedbackCsv", retrainForm.feedback_csv);
    } else {
      localStorage.removeItem("artstyleRetrainFeedbackCsv");
    }
  }, [retrainForm.feedback_csv]);

  function chooseFile(selectedFile) {
    setError("");
    setResult(null);
    setTaskId("");
    setStatus("");
    setFeedbackStatus("");
    setFeedbackError("");

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
      setSelectedStyleCode(predictionResult.top_prediction?.style?.code || "Contemporary_Art");
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
    setFeedbackStatus("");
    setFeedbackError("");
    setSelectedStyleCode("Contemporary_Art");
  }

  async function handleSubmitFeedback(event) {
    event.preventDefault();

    if (!result?.task_id) {
      setFeedbackError("Classification result is required before submitting feedback.");
      return;
    }

    setIsSubmittingFeedback(true);
    setFeedbackError("");
    setFeedbackStatus("");

    try {
      const feedback = await submitPredictionFeedback(result.task_id, selectedStyleCode);
      setFeedbackStatus(
        `Saved feedback #${feedback.feedback_id}: ${feedback.predicted_style_code} → ${feedback.correct_style_code}.`
      );
    } catch (caughtError) {
      setFeedbackError(caughtError.message || "Could not save feedback.");
    } finally {
      setIsSubmittingFeedback(false);
    }
  }

  async function runAdminAction(title, action) {
    if (!adminToken.trim()) {
      setAdminError("Enter admin token first.");
      return;
    }

    setIsAdminLoading(true);
    setAdminError("");

    try {
      const data = await action(adminToken.trim());
      setAdminResult({ title, data });
      if (title === "Retrain feedback export" && data?.payload_preview?.csv_path) {
        setRetrainForm((current) => ({
          ...current,
          feedback_csv: data.payload_preview.csv_path,
        }));
      }
    } catch (caughtError) {
      setAdminError(caughtError.message || "Admin request failed.");
    } finally {
      setIsAdminLoading(false);
    }
  }

  async function pollRetrainJob(token, job) {
    let currentJob = job;
    setAdminResult({ title: `Retrain job ${currentJob.job_id}`, data: currentJob });

    while (currentJob.status === "running") {
      await sleep(RETRAIN_POLLING_DELAY_MS);
      currentJob = await getRetrainJob(token, currentJob.job_id);
      setAdminResult({ title: `Retrain job ${currentJob.job_id}`, data: currentJob });
    }

    return currentJob;
  }

  function updateSwitchForm(field, value) {
    setSwitchForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function updateRetrainForm(field, value) {
    setRetrainForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  async function handleSwitchModel(event) {
    event.preventDefault();

    await runAdminAction("Switch model", (token) =>
      switchModel(token, {
        model_source: switchForm.model_source,
        model_name: switchForm.model_name.trim() || undefined,
        model_version: switchForm.model_version.trim(),
      })
    );
  }

  async function handleRunRetrain(event) {
    event.preventDefault();

    if (!retrainForm.feedback_csv.trim()) {
      setAdminError("Run Export feedback CSV first or paste the CSV path.");
      return;
    }

    await runAdminAction("Run retrain", async (token) => {
      const job = await runRetrain(token, {
        feedback_csv: retrainForm.feedback_csv.trim(),
        min_new_feedback: Number(retrainForm.min_new_feedback),
        feedback_repeat: Number(retrainForm.feedback_repeat),
        epochs: Number(retrainForm.epochs),
        batch_size: Number(retrainForm.batch_size),
        min_val_acc: Number(retrainForm.min_val_acc),
        device: retrainForm.device,
        activate: Boolean(retrainForm.activate),
      });
      return pollRetrainJob(token, job);
    });
  }

  if (isAdminRoute) {
    return (
      <AdminPanel
        adminToken={adminToken}
        adminResult={adminResult}
        adminError={adminError}
        isAdminLoading={isAdminLoading}
        switchForm={switchForm}
        retrainForm={retrainForm}
        onAdminTokenChange={setAdminToken}
        onLoadCurrentModel={() => runAdminAction("Current model", getCurrentModel)}
        onLoadAvailableModels={() => runAdminAction("Available models", getAvailableModels)}
        onReloadWorkers={() => runAdminAction("Reload workers", reloadWorkers)}
        onExportRetrainFeedback={() => runAdminAction("Retrain feedback export", exportRetrainFeedback)}
        onListRetrainJobs={() => runAdminAction("Retrain jobs", listRetrainJobs)}
        onSwitchFormChange={updateSwitchForm}
        onSwitchModel={handleSwitchModel}
        onRetrainFormChange={updateRetrainForm}
        onRunRetrain={handleRunRetrain}
      />
    );
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
        <div className="hero-actions">
          <a className="api-pill" href="/admin">Admin console</a>
          <div className="api-pill">API: {API_BASE_URL}/v1</div>
        </div>
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
          <FeedbackPanel
            result={result}
            selectedStyleCode={selectedStyleCode}
            feedbackStatus={feedbackStatus}
            feedbackError={feedbackError}
            isSubmittingFeedback={isSubmittingFeedback}
            onSelectedStyleCodeChange={setSelectedStyleCode}
            onSubmitFeedback={handleSubmitFeedback}
          />
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
