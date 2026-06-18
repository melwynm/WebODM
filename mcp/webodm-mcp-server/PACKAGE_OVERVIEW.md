# Package Overview

Start here if you just pulled this package into the WebODM repo.

## What This Package Is

This folder contains a standalone MCP server for this WebODM fork. It talks to the running WebODM API over HTTP and exposes WebODM operations as MCP tools for Claude Desktop or any other MCP client.

## Why It Lives in Its Own Folder

The root WebODM repository already has a package.json for the frontend build. This MCP server ships with its own package.json so we can install and version MCP dependencies without disturbing the main app.

## Folder Layout

- `index.js`: MCP entry point.
- `lib/common.js`: shared HTTP, auth, schema, and URL helpers.
- `lib/tool-definitions.js`: MCP tool metadata.
- `lib/handlers.js`: WebODM API handlers for each tool.
- `test-contract.js`: non-interactive tool/schema/handler contract test.
- `test-handlers.js`: mock WebODM HTTP integration test for endpoint mappings and auth.
- `test-server.js`: MCP SDK stdio handshake and list-tools test.
- `test-connection.js`: live connection test against a running WebODM instance.
- `generate-tool.js`: snippet generator for new tools.
- `MAINTENANCE.md`: detailed workflow for keeping this package aligned with WebODM changes.
- `API_MAPPING.md`: endpoint-to-tool reference for this fork.

## Fastest Path

1. Run `npm install` in this folder.
2. Run `npm test` and confirm the contract test passes.
3. Run `npm run test:connection` when a real WebODM credential is available.
4. Add the example block from `claude_desktop_config.example.json` to your MCP client config.
5. Start using the tools.

## What Was Fixed From the Original ZIP

- Added the missing `PACKAGE_OVERVIEW.md` that the archive referenced but did not include.
- Switched auth guidance and implementation to explicit auth schemes so the MCP layer can use both JWT/Bearer tokens and permanent `Token` API keys.
- Added MCP coverage for the permanent token endpoints in this fork.
- Updated the connection tester to validate both JWT bootstrap and permanent token auth.
- Split the server into smaller maintenance-friendly modules instead of one giant file.
- Synchronized MCP coverage with commercial readiness, delivery exports, reports, review evidence, client shares, feature validation, monitoring timeline, 3D QA, and object detection including deer.
