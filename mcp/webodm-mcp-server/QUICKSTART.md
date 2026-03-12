# Quickstart

## 1. Install

```bash
cd mcp/webodm-mcp-server
npm install
```

## 2. Set Your WebODM URL

Copy .env.example to .env if you want a local file, or set WEBODM_BASE_URL in your MCP client config.

Default value:

```bash
WEBODM_BASE_URL=http://localhost:8000
```

## 3. Verify the Connection

```bash
npm test
```

This prompts for your username and password, requests a token from /api/token-auth/, and checks a few core endpoints.

## 4. Register the MCP Server

Use the example in claude_desktop_config.example.json and point it at:

```text
<absolute-path-to-WebODM>/mcp/webodm-mcp-server/index.js
```

## 5. Start Using Tools

A typical first flow is:

1. webodm_authenticate
2. webodm_list_projects
3. webodm_list_tasks
4. webodm_get_task

## Useful Commands

```bash
npm start
npm run dev
npm run smoke
npm run generate
```
