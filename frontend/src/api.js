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
