# WebODM MCP Server

This package adds a standalone MCP server for the WebODM fork in this repository. It exposes common WebODM operations as MCP tools so an MCP client can inspect projects, create tasks, poll exports, and work with the processing-node layer without custom one-off scripts.

## Highlights

- Bearer-token authentication that matches this WebODM fork.
- Core project, task, processing-node, preset, monitoring, and worker tools.
- Direct URL helpers for downloads and exported assets.
- A repo-local maintenance workflow for adding tools when the WebODM API changes.
- No interference with the root WebODM package.json.

## Package Structure

```text
mcp/webodm-mcp-server/
  index.js
  lib/common.js
  lib/tool-definitions.js
  lib/handlers.js
  test-connection.js
  generate-tool.js
  PACKAGE_OVERVIEW.md
  QUICKSTART.md
  MAINTENANCE.md
  API_MAPPING.md
```

## Installation

```bash
cd mcp/webodm-mcp-server
npm install
```

## Configuration

Set WEBODM_BASE_URL to the URL of the running WebODM instance. Example:

```bash
WEBODM_BASE_URL=http://localhost:8000
```

If you already have a valid access token, you can also set WEBODM_TOKEN. Otherwise the recommended flow is to call webodm_authenticate from the MCP client.

## Claude Desktop Example

```json
{
  "mcpServers": {
    "webodm": {
      "command": "node",
      "args": [
        "/absolute/path/to/WebODM/mcp/webodm-mcp-server/index.js"
      ],
      "env": {
        "WEBODM_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

## Tool Coverage

The server covers these API areas:

- Projects: list, get, create, patch, duplicate, permissions, and the special edit endpoint.
- Tasks: list, get, create, partial upload flow, import, output, cancel, restart, remove, compact, duplicate.
- Assets: download URLs, raw asset URLs, raster metadata endpoints, export requests.
- 3D and monitoring: scene read/write, camera view write, monitoring candidates, monitoring compare.
- Processing nodes: list, get, create, patch, delete, shared options.
- Presets: list, get, create, patch, delete.
- Workers and utilities: background task polling, worker result URLs, task status lookup, pending-action lookup.

## Development Notes

This package is intentionally data-driven:

- lib/tool-definitions.js contains the MCP schema visible to clients.
- lib/handlers.js contains one handler per tool.
- lib/common.js contains the auth, HTTP, multipart, and response helpers.

If WebODM changes, update those three files together and then refresh API_MAPPING.md.

## Verification

```bash
npm run smoke
npm test
```

- npm run smoke checks JavaScript syntax for the core scripts.
- npm test runs the interactive connection check against a real WebODM instance.

## Maintenance Workflow

Read these in order when you want to extend the package:

1. PACKAGE_OVERVIEW.md
2. MAINTENANCE_README.md
3. MAINTENANCE.md
4. API_MAPPING.md
