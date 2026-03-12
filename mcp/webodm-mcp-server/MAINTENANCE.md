# Maintenance Guide

## Goal

Keep the MCP layer synchronized with the WebODM API in this repository without turning the package into a fragile one-off integration.

## Architecture

The package is intentionally split by responsibility:

- index.js: MCP bootstrap only.
- lib/common.js: shared auth, HTTP, schema, and multipart helpers.
- lib/tool-definitions.js: user-facing MCP tool metadata.
- lib/handlers.js: endpoint-specific logic.

## Change Workflow

### 0. Check Whether MCP Is Affected

If the WebODM change is internal only, such as plugin loading, startup warnings, worker wiring, or UI behavior, and it does not change `app/api/`, auth behavior, or response shapes, the MCP package usually does not need a code update.

In that case:

- leave `lib/handlers.js` and `lib/tool-definitions.js` alone
- do not touch `API_MAPPING.md`
- optionally refresh maintenance notes if the change clarifies future MCP triage

### 1. Confirm the API Contract

Before touching the MCP package, inspect:

- app/api/urls.py
- the target view or viewset in app/api/
- any relevant tests in app/tests/
- the public docs in slate/source/includes/reference/

### 2. Decide Whether the Existing Tool Should Change

Ask these questions:

- Is the endpoint path still the same?
- Did the request body change?
- Did the response shape change?
- Is this a new endpoint that deserves a new MCP tool?

If only the request or response changed, update the existing handler and tool schema. Avoid creating duplicates.

### 3. Update the Handler

Make the behavior change in lib/handlers.js first. Keep handler logic small and move any reusable logic into lib/common.js.

Examples of changes that belong in common.js:

- shared request helpers
- auth behavior
- multipart upload helpers
- direct URL helpers
- response parsing rules

### 4. Update the Tool Schema

Reflect the MCP-visible argument contract in lib/tool-definitions.js.

A good schema change should:

- keep names stable unless there is a real breaking change
- use clear descriptions
- prefer generic payload/query objects when the WebODM endpoint is intentionally flexible

### 5. Refresh the Mapping

Update API_MAPPING.md so future changes have one source of truth.

### 6. Verify

```bash
npm run smoke
npm test
```

## Adding a New Tool

### Fast path

```bash
npm run generate
```

This creates a markdown snippet in generated/ with a candidate schema block and a handler stub.

### Manual checklist

1. Add a handler in lib/handlers.js.
2. Add the tool metadata in lib/tool-definitions.js.
3. Add a short note to API_MAPPING.md.
4. Add or update an example in EXAMPLES.md if the tool is user-facing.
5. Run npm run smoke.
6. Run npm test.

## Editing Existing Tools Safely

### Prefer additions over renames

If you can extend a payload object or query object without renaming a tool, do that.

### Preserve auth behavior

This fork uses Bearer tokens. Do not switch the Authorization header back to JWT.

### Preserve project-list behavior

This fork returns an array from /api/projects/ when page is omitted. Do not assume pagination unless page is provided.

## Common Scenarios

### New task action endpoint

Example: POST /api/projects/{project_id}/tasks/{task_id}/requeue/

1. Add a handler calling requestJson(..., { method: "POST" }).
2. Add the MCP schema with project_id and task_id.
3. Map it in API_MAPPING.md.
4. Verify against a real instance.

### New project metadata field

If the field belongs to the serializer, update the project create and update payload descriptions. If it only works through the special edit endpoint, document that in the edit-project tool.

### New export option

If export_task_asset already accepts a flexible payload, you might only need a docs update. Add the new payload field to API_MAPPING.md and EXAMPLES.md.

## Breaking Change Checklist

When WebODM changes an endpoint path or removes a field:

1. Update the handler.
2. Update the schema.
3. Add a note in API_MAPPING.md under Notes.
4. Update README.md or TROUBLESHOOTING.md if users will notice the change.

## Release Notes Suggestion

When you make non-trivial changes, add a short section to your PR or commit message covering:

- WebODM endpoint changed
- MCP tool added or updated
- docs refreshed
- smoke and live checks performed
