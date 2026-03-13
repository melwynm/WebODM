import fs from "fs";
import path from "path";
import FormData from "form-data";
import fetch from "node-fetch";

export const WEBODM_BASE_URL = normalizeBaseUrl(process.env.WEBODM_BASE_URL || "http://localhost:8000");
export const AUTH_SCHEMES = {
  BEARER: "Bearer",
  TOKEN: "Token",
};

let authState = getInitialAuthState();

export const TASK_STATUS = {
  10: {
    name: "QUEUED",
    description: "Task files were uploaded and are waiting for processing.",
  },
  20: {
    name: "RUNNING",
    description: "Task processing is currently in progress.",
  },
  30: {
    name: "FAILED",
    description: "Task processing failed.",
  },
  40: {
    name: "COMPLETED",
    description: "Task processing completed and assets should be available.",
  },
  50: {
    name: "CANCELED",
    description: "Task processing was canceled.",
  },
};

export const PENDING_ACTIONS = {
  1: {
    name: "CANCEL",
    description: "The task is in the process of being canceled.",
  },
  2: {
    name: "REMOVE",
    description: "The task is in the process of being removed.",
  },
  3: {
    name: "RESTART",
    description: "The task is in the process of being restarted.",
  },
  4: {
    name: "RESIZE",
    description: "The task is resizing inputs before processing.",
  },
  5: {
    name: "IMPORT",
    description: "The task is importing processed assets.",
  },
  6: {
    name: "COMPACT",
    description: "The task is compacting its stored assets.",
  },
};

export const openObjectSchema = {
  type: "object",
  description: "Any JSON object supported by the target WebODM endpoint.",
  additionalProperties: true,
};

export const optionsSchema = {
  type: "array",
  description: "Processing options in WebODM name/value format.",
  items: {
    type: "object",
    properties: {
      name: {
        type: "string",
        description: "Option name.",
      },
      value: {
        description: "Option value.",
      },
    },
    required: ["name", "value"],
    additionalProperties: false,
  },
};

export const projectPermissionSchema = {
  type: "array",
  description: "Project permission entries used by the special project edit endpoint.",
  items: {
    type: "object",
    properties: {
      username: {
        type: "string",
        description: "Target username.",
      },
      owner: {
        type: "boolean",
        description: "Whether this user is the project owner.",
      },
      permissions: {
        type: "array",
        description: "Project permissions to assign.",
        items: {
          type: "string",
          enum: ["view", "add", "change", "delete"],
        },
      },
    },
    required: ["username", "permissions"],
    additionalProperties: false,
  },
};

export function normalizeBaseUrl(url) {
  return String(url).replace(/\/+$/, "");
}

export function schema(properties, required = []) {
  return {
    type: "object",
    properties,
    additionalProperties: false,
    ...(required.length > 0 ? { required } : {}),
  };
}

export function stringField(description) {
  return {
    type: "string",
    description,
  };
}

export function numberField(description) {
  return {
    type: "number",
    description,
  };
}

export function booleanField(description) {
  return {
    type: "boolean",
    description,
  };
}

export function hasValue(value) {
  return value !== undefined && value !== null && value !== "";
}

export function compactObject(value) {
  return Object.fromEntries(
    Object.entries(value || {}).filter(([, entry]) => hasValue(entry))
  );
}

export function getAuthToken() {
  return authState?.token || null;
}

export function getAuthScheme() {
  return authState?.scheme || null;
}

export function setAuthToken(token, scheme = AUTH_SCHEMES.BEARER) {
  authState = {
    token,
    scheme: normalizeAuthScheme(scheme),
  };
}

export function ensureTokenAvailable() {
  if (!authState?.token) {
    throw new Error("No WebODM credentials are loaded. Call webodm_authenticate first or set WEBODM_API_KEY / WEBODM_TOKEN.");
  }
}

export function assertFileExists(filePath, label) {
  const absolutePath = path.resolve(filePath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`${label} not found: ${absolutePath}`);
  }
  return absolutePath;
}

export function appendMultipartField(form, key, value) {
  if (!hasValue(value)) {
    return;
  }

  if (Array.isArray(value) || (typeof value === "object" && value !== null)) {
    form.append(key, JSON.stringify(value));
    return;
  }

  form.append(key, String(value));
}

export function appendTaskFields(form, payload) {
  for (const [key, value] of Object.entries(payload || {})) {
    appendMultipartField(form, key, value);
  }
}

export function encodePathPreservingSlashes(value) {
  return String(value)
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

export function buildUrl(endpoint, query) {
  const url = new URL(`${WEBODM_BASE_URL}${endpoint}`);
  for (const [key, value] of Object.entries(query || {})) {
    if (!hasValue(value)) {
      continue;
    }
    if (Array.isArray(value)) {
      url.searchParams.set(key, value.join(","));
    } else if (typeof value === "object") {
      url.searchParams.set(key, JSON.stringify(value));
    } else {
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

export function buildUrlResult(endpoint, query, includeJwtQuery, requiresAuth = true) {
  const result = {
    url: buildUrl(endpoint, query).toString(),
    requires_auth: requiresAuth,
  };

  if (includeJwtQuery) {
    ensureTokenAvailable();
    if (getAuthScheme() !== AUTH_SCHEMES.BEARER) {
      throw new Error("include_jwt_query only works when the current MCP session is using a JWT/Bearer token.");
    }
    const authenticatedUrl = buildUrl(endpoint, {
      ...(query || {}),
      jwt: getAuthToken(),
    });
    result.authenticated_url = authenticatedUrl.toString();
  }

  return result;
}

export async function uploadMultipart(endpoint, form) {
  const url = buildUrl(endpoint);
  const headers = {
    ...form.getHeaders(),
  };

  applyAuthHeader(headers);

  const response = await fetch(url, {
    method: "POST",
    headers,
    body: form,
  });

  return parseResponse(response, url.toString(), "json");
}

export async function requestJson(endpoint, options = {}) {
  const {
    method = "GET",
    query,
    json,
    form,
    headers = {},
    skipAuth = false,
    responseType = "json",
  } = options;

  const requestHeaders = {
    ...headers,
  };
  const url = buildUrl(endpoint, query);
  let body;

  if (!skipAuth) {
    applyAuthHeader(requestHeaders);
  }

  if (json !== undefined) {
    requestHeaders["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form !== undefined) {
    requestHeaders["Content-Type"] = "application/x-www-form-urlencoded";
    const encoded = new URLSearchParams();
    for (const [key, value] of Object.entries(form || {})) {
      if (!hasValue(value)) {
        continue;
      }
      if (Array.isArray(value) || (typeof value === "object" && value !== null)) {
        encoded.set(key, JSON.stringify(value));
      } else {
        encoded.set(key, String(value));
      }
    }
    body = encoded.toString();
  }

  const response = await fetch(url, {
    method,
    headers: requestHeaders,
    body,
  });

  return parseResponse(response, url.toString(), responseType);
}

export async function parseResponse(response, url, responseType) {
  if (response.status === 401 || response.status === 403) {
    const maybeJson = await safeJson(response);
    if (maybeJson && maybeJson.detail === "Signature has expired.") {
      throw new Error("WebODM access token has expired. Authenticate again.");
    }
    if (maybeJson && maybeJson.detail === "Invalid API token") {
      throw new Error("WebODM API token was rejected. If you regenerated it, load the new token before retrying.");
    }
    if (maybeJson) {
      throw new Error(`WebODM request failed (${response.status}) for ${url}: ${JSON.stringify(maybeJson)}`);
    }
  }

  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      detail = parsed.detail || parsed.error || JSON.stringify(parsed);
    } catch {
      detail = body;
    }
    throw new Error(`WebODM request failed (${response.status} ${response.statusText}) for ${url}: ${detail}`);
  }

  if (responseType === "empty" || response.status === 204) {
    return {
      success: true,
    };
  }

  if (responseType === "text") {
    return response.text();
  }

  if (responseType === "auto") {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return response.json();
    }
    return response.text();
  }

  return response.json();
}

async function safeJson(response) {
  const cloned = response.clone();
  try {
    return await cloned.json();
  } catch {
    return null;
  }
}

export function toolSuccess(result) {
  return {
    content: [
      {
        type: "text",
        text: typeof result === "string" ? result : JSON.stringify(result, null, 2),
      },
    ],
  };
}

export function toolError(message) {
  return {
    content: [
      {
        type: "text",
        text: `Error: ${message}`,
      },
    ],
    isError: true,
  };
}

export function createMultipartForm() {
  return new FormData();
}

function normalizeAuthScheme(value) {
  const normalized = String(value || AUTH_SCHEMES.BEARER).trim().toLowerCase();

  if (normalized === "bearer" || normalized === "jwt") {
    return AUTH_SCHEMES.BEARER;
  }

  if (normalized === "token") {
    return AUTH_SCHEMES.TOKEN;
  }

  throw new Error(`Unsupported WebODM auth scheme: ${value}`);
}

function getInitialAuthState() {
  if (process.env.WEBODM_API_KEY) {
    return {
      token: process.env.WEBODM_API_KEY,
      scheme: AUTH_SCHEMES.TOKEN,
    };
  }

  if (process.env.WEBODM_TOKEN) {
    return {
      token: process.env.WEBODM_TOKEN,
      scheme: normalizeAuthScheme(process.env.WEBODM_TOKEN_TYPE || AUTH_SCHEMES.BEARER),
    };
  }

  return null;
}

function applyAuthHeader(headers) {
  if (!authState?.token || headers.Authorization) {
    return headers;
  }

  headers.Authorization = `${authState.scheme} ${authState.token}`;
  return headers;
}
