# Maintenance Readme

This MCP package is meant to evolve with the WebODM fork in this repository.

## The Three Files That Matter Most

- lib/tool-definitions.js: what the MCP client sees.
- lib/handlers.js: how each tool talks to WebODM.
- API_MAPPING.md: the contract between this package and the WebODM API.

## Minimal Workflow for Any API Change

1. Confirm the WebODM endpoint exists in app/api/urls.py and the corresponding view.
2. Add or update a handler in lib/handlers.js.
3. Add or update the MCP schema in lib/tool-definitions.js.
4. Refresh API_MAPPING.md.
5. Run npm run smoke.
6. Run npm test against a real WebODM instance.

## When to Use generate-tool.js

Use generate-tool.js when you add a brand new endpoint and want a quick scaffold for the schema and handler. It saves snippets into generated/ so you can review them before moving anything into the real files.
