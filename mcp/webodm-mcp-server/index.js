#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { TOOL_HANDLERS } from "./lib/handlers.js";
import { TOOL_DEFINITIONS } from "./lib/tool-definitions.js";
import { MCP_SERVER_VERSION, WEBODM_BASE_URL, toolError, toolSuccess } from "./lib/common.js";

const server = new Server(
  {
    name: "webodm-mcp-server",
    version: MCP_SERVER_VERSION,
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOL_DEFINITIONS,
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const toolName = request.params.name;
  const args = request.params.arguments || {};
  const handler = TOOL_HANDLERS[toolName];

  if (!handler) {
    return toolError(`Unknown tool: ${toolName}`);
  }

  try {
    const result = await handler(args);
    return toolSuccess(result);
  } catch (error) {
    return toolError(error instanceof Error ? error.message : String(error));
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error(`WebODM MCP server listening on stdio for ${WEBODM_BASE_URL}`);
}

main().catch((error) => {
  console.error(`Fatal error: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
