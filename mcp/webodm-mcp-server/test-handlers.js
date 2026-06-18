#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

const requests = [];
const server = http.createServer((request, response) => {
  const chunks = [];
  request.on("data", (chunk) => chunks.push(chunk));
  request.on("end", () => {
    const entry = {
      method: request.method,
      url: request.url,
      authorization: request.headers.authorization,
      contentType: request.headers["content-type"] || "",
      body: Buffer.concat(chunks).toString("utf8"),
    };
    requests.push(entry);
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify(entry));
  });
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
process.env.WEBODM_BASE_URL = `http://127.0.0.1:${address.port}`;
process.env.WEBODM_API_KEY = "test-api-key";

const { TOOL_HANDLERS } = await import("./lib/handlers.js");
const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "webodm-mcp-"));
const overlayPath = path.join(tempDir, "overlay.geojson");
const photoPath = path.join(tempDir, "photo.jpg");
fs.writeFileSync(overlayPath, '{"type":"FeatureCollection","features":[]}');
fs.writeFileSync(photoPath, "test-image");

try {
  let result = await TOOL_HANDLERS.webodm_get_commercial_readiness({ project_id: 7, package: "solar_inspection" });
  assert.equal(result.method, "GET");
  assert.equal(result.url, "/api/projects/7/commercial/readiness?package=solar_inspection");
  assert.equal(result.authorization, "Token test-api-key");

  result = await TOOL_HANDLERS.webodm_update_commercial_readiness({
    project_id: 7,
    patch: { human_reviewed: true },
  });
  assert.equal(result.method, "PATCH");
  assert.deepEqual(JSON.parse(result.body), { human_reviewed: true });

  result = await TOOL_HANDLERS.webodm_get_progress_report({
    project_id: 7,
    template: "solar_inspection",
    format: "json",
  });
  assert.equal(result.url, "/api/projects/7/reports/progress?template=solar_inspection&format=json");

  result = await TOOL_HANDLERS.webodm_detect_ai_issues({
    project_id: 7,
    task_id: "task-uuid",
    source: "orthophoto",
    create: false,
    max_images: 2,
  });
  assert.equal(result.method, "POST");
  assert.deepEqual(JSON.parse(result.body), {
    task: "task-uuid",
    source: "orthophoto",
    create: false,
    max_images: 2,
  });

  result = await TOOL_HANDLERS.webodm_start_object_detection({ task_id: "task-uuid", model: "deer" });
  assert.equal(result.url, "/api/plugins/objdetect/task/task-uuid/detect");
  assert.deepEqual(JSON.parse(result.body), { model: "deer" });

  result = await TOOL_HANDLERS.webodm_update_feature_validation({
    key: "commercial-readiness-checklist",
    patch: { status: "tested" },
  });
  assert.equal(result.url, "/api/feature-validations/commercial-readiness-checklist/");

  result = await TOOL_HANDLERS.webodm_create_project_issue({
    project_id: 7,
    payload: { title: "Review deer count", status: "in_review" },
  });
  assert.equal(result.url, "/api/projects/7/issues/");

  result = await TOOL_HANDLERS.webodm_get_monitoring_timeline({ project_id: 7, task_id: "task-uuid" });
  assert.equal(result.url, "/api/projects/7/monitoring/timeline?task=task-uuid");

  result = await TOOL_HANDLERS.webodm_get_textured_model_qa({ project_id: 7, task_id: "task-uuid" });
  assert.equal(result.url, "/api/projects/7/tasks/task-uuid/3d/qa");

  result = await TOOL_HANDLERS.webodm_create_client_share({
    project_id: 7,
    payload: { name: "Client", role: "viewer" },
  });
  assert.equal(result.url, "/api/projects/7/client-shares/");

  result = await TOOL_HANDLERS.webodm_create_design_overlay({
    project_id: 7,
    file_path: overlayPath,
    name: "Site plan",
  });
  assert.equal(result.url, "/api/projects/7/design-overlays/");
  assert.match(result.contentType, /^multipart\/form-data; boundary=/);

  result = await TOOL_HANDLERS.webodm_create_field_photo({
    project_id: 7,
    image_path: photoPath,
    payload: { task: "task-uuid", name: "North field" },
  });
  assert.equal(result.url, "/api/projects/7/field-photos/");
  assert.match(result.contentType, /^multipart\/form-data; boundary=/);

  const delivery = await TOOL_HANDLERS.webodm_get_delivery_export_url({
    project_id: 7,
    template: "solar_inspection",
  });
  assert.equal(delivery.url, `${process.env.WEBODM_BASE_URL}/api/projects/7/delivery/export?template=solar_inspection`);
  assert.equal(delivery.requires_auth, true);

  assert(requests.length >= 11);
  console.log(`MCP handler integration OK: ${requests.length} WebODM requests verified.`);
} finally {
  fs.rmSync(tempDir, { recursive: true, force: true });
  await new Promise((resolve) => server.close(resolve));
}
