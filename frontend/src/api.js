export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const API_PREFIX = "/v1";

function getErrorMessage(data, status) {
  if (data && typeof data === "object") {
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    if (typeof data.error_message === "string") return data.error_message;
  }

  if (typeof data === "string" && data.trim()) return data;
  return `Request failed with status ${status}`;
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    throw new Error(getErrorMessage(data, response.status));
  }

  return data;
}

export async function uploadImage(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/upload`, {
    method: "POST",
    body: formData,
  });

  return parseResponse(response);
}

export async function getTaskStatus(taskId) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/tasks/${taskId}`);
  return parseResponse(response);
}

export async function getTaskResult(taskId) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/tasks/${taskId}/result`);
  return parseResponse(response);
}

export async function submitPredictionFeedback(taskId, correctStyleCode) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/tasks/${taskId}/feedback`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      correct_style_code: correctStyleCode,
    }),
  });

  return parseResponse(response);
}

function buildAdminHeaders(adminToken) {
  return {
    "X-Admin-Token": adminToken,
  };
}

export async function getCurrentModel(adminToken) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/models/current`, {
    headers: buildAdminHeaders(adminToken),
  });

  return parseResponse(response);
}

export async function getAvailableModels(adminToken) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/models/available`, {
    headers: buildAdminHeaders(adminToken),
  });

  return parseResponse(response);
}

export async function switchModel(adminToken, payload) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/models/switch`, {
    method: "POST",
    headers: {
      ...buildAdminHeaders(adminToken),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseResponse(response);
}

export async function reloadWorkers(adminToken) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/models/reload-workers`, {
    method: "POST",
    headers: buildAdminHeaders(adminToken),
  });

  return parseResponse(response);
}

export async function exportRetrainFeedback(adminToken) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/retrain/export`, {
    method: "POST",
    headers: buildAdminHeaders(adminToken),
  });

  return parseResponse(response);
}

export async function runRetrain(adminToken, payload) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/retrain/run`, {
    method: "POST",
    headers: {
      ...buildAdminHeaders(adminToken),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseResponse(response);
}

export async function getRetrainJob(adminToken, jobId) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/retrain/jobs/${jobId}`, {
    headers: buildAdminHeaders(adminToken),
  });

  return parseResponse(response);
}

export async function listRetrainJobs(adminToken) {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}/admin/retrain/jobs`, {
    headers: buildAdminHeaders(adminToken),
  });

  return parseResponse(response);
}
