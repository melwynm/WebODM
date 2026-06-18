#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { MCP_SERVER_VERSION } from "./lib/common.js";
import { TOOL_HANDLERS } from "./lib/handlers.js";
import { TOOL_DEFINITIONS } from "./lib/tool-definitions.js";

const root = path.dirname(fileURLToPath(import.meta.url));
const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const definitionNames = TOOL_DEFINITIONS.map((definition) => definition.name);
const handlerNames = Object.keys(TOOL_HANDLERS);

assert.equal(MCP_SERVER_VERSION, packageJson.version, "Server and package versions must match.");
assert.equal(new Set(definitionNames).size, definitionNames.length, "Tool names must be unique.");
assert.deepEqual(
  [...definitionNames].sort(),
  [...handlerNames].sort(),
  "Every tool definition must have exactly one handler."
);

for (const definition of TOOL_DEFINITIONS) {
  assert.equal(definition.inputSchema?.type, "object", `${definition.name} must expose an object input schema.`);
  const taskIdSchema = definition.inputSchema?.properties?.task_id;
  if (taskIdSchema) {
    assert.equal(taskIdSchema.type, "string", `${definition.name}.task_id must accept WebODM task UUIDs.`);
  }
}

const requiredCurrentTools = [
  "webodm_get_monitoring_timeline",
  "webodm_get_textured_model_qa",
  "webodm_get_progress_report",
  "webodm_get_commercial_readiness",
  "webodm_update_commercial_readiness",
  "webodm_get_delivery_export_url",
  "webodm_detect_ai_issues",
  "webodm_start_object_detection",
  "webodm_list_feature_validations",
  "webodm_list_project_issues",
  "webodm_list_design_overlays",
  "webodm_list_field_photos",
  "webodm_list_client_shares",
];

for (const toolName of requiredCurrentTools) {
  assert(definitionNames.includes(toolName), `Missing current WebODM MCP tool: ${toolName}`);
}

const objectDetectionTool = TOOL_DEFINITIONS.find((definition) => definition.name === "webodm_start_object_detection");
assert(objectDetectionTool.inputSchema.properties.model.enum.includes("deer"), "Object detection must expose the deer model.");

console.log(`MCP contract OK: ${TOOL_DEFINITIONS.length} tools, version ${MCP_SERVER_VERSION}.`);
