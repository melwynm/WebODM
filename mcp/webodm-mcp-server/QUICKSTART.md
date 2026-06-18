# Quickstart

## 1. Install

```bash
cd mcp/webodm-mcp-server
npm install
```

## 2. Set Your WebODM URL and Optional Auth

Copy `.env.example` to `.env` if you want a local file, or set these values in your MCP client config.

Default value:

```bash
WEBODM_BASE_URL=http://localhost:8000
```

Recommended for long-lived automation:

```bash
WEBODM_API_KEY=your_permanent_api_key_here
```

If you do not have a permanent API key yet, you can start with `webodm_authenticate` and then switch the running session by calling:

```json
{
  "store_for_session": true
}
```

with `webodm_get_api_token`.

## 3. Verify the Connection

```bash
npm test
npm run test:connection
```

`npm test` validates JavaScript syntax and the MCP tool/handler contract without credentials. `npm run test:connection` prompts for your username and password, requests a JWT from `/api/token-auth/`, verifies `/api/token/`, then checks core endpoints using permanent `Token` auth.

For non-interactive live verification, set `WEBODM_USERNAME` and `WEBODM_PASSWORD` before running `npm run test:connection`.

## 4. Register the MCP Server

Use the example in `claude_desktop_config.example.json` and point it at:

```text
<absolute-path-to-WebODM>/mcp/webodm-mcp-server/index.js
```

## 5. Start Using Tools

A typical first flow is:

1. `webodm_authenticate`
2. `webodm_get_api_token`
3. `webodm_list_projects`
4. `webodm_list_tasks`
5. `webodm_get_task`

If your MCP client already injects `WEBODM_API_KEY`, you can skip `webodm_authenticate` and `webodm_get_api_token`.

## Useful Commands

```bash
npm start
npm run dev
npm run smoke
npm run generate
```
