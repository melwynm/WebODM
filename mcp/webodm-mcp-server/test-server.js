#!/usr/bin/env node

import assert from "node:assert/strict";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(fileURLToPath(import.meta.url));
const transport = new StdioClientTransport({
  command: process.execPath,
  args: [path.join(root, "index.js")],
  env: {
    ...process.env,
    WEBODM_BASE_URL: "http://localhost:8000",
  },
  stderr: "pipe",
});
const client = new Client({ name: "webodm-mcp-contract-test", version: "1.0.0" });

try {
  await client.connect(transport);
  const result = await client.listTools();
  const names = result.tools.map((tool) => tool.name);

  assert(names.length >= 80, `Expected at least 80 MCP tools, received ${names.length}.`);
  assert(names.includes("webodm_get_commercial_readiness"));
  assert(names.includes("webodm_start_object_detection"));

  console.log(`MCP stdio server OK: ${names.length} tools listed.`);
} finally {
  await client.close();
}
