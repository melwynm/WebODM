#!/usr/bin/env node

import fetch from "node-fetch";
import readline from "readline";

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
});

function ask(prompt) {
  return new Promise((resolve) => {
    rl.question(prompt, resolve);
  });
}

function normalizeBaseUrl(url) {
  return (url || "http://localhost:8000").replace(/\/+$/, "");
}

function countProjects(payload) {
  if (Array.isArray(payload)) {
    return payload.length;
  }
  if (payload && Array.isArray(payload.results)) {
    return payload.results.length;
  }
  return 0;
}

async function main() {
  const baseUrl = normalizeBaseUrl(process.env.WEBODM_BASE_URL || (await ask("WebODM URL [http://localhost:8000]: ")) || "http://localhost:8000");
  const username = process.env.WEBODM_USERNAME || (await ask("Username: "));
  const password = process.env.WEBODM_PASSWORD || (await ask("Password: "));

  console.log();
  console.log(`Checking ${baseUrl} ...`);

  try {
    const availabilityResponse = await fetch(`${baseUrl}/api/projects/`);
    if (![200, 401, 403].includes(availabilityResponse.status)) {
      throw new Error(`Unexpected status ${availabilityResponse.status} from /api/projects/`);
    }
    console.log("1. WebODM is reachable.");
  } catch (error) {
    console.error(`1. Cannot reach WebODM: ${error.message}`);
    process.exit(1);
  }

  let jwtToken;
  try {
    const authResponse = await fetch(`${baseUrl}/api/token-auth/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: `username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
    });

    if (!authResponse.ok) {
      throw new Error(await authResponse.text());
    }

    const payload = await authResponse.json();
    jwtToken = payload.token;
    console.log("2. JWT authentication succeeded.");
  } catch (error) {
    console.error(`2. Authentication failed: ${error.message}`);
    process.exit(1);
  }

  let apiKey;
  try {
    const tokenResponse = await fetch(`${baseUrl}/api/token/`, {
      headers: {
        Authorization: `Bearer ${jwtToken}`,
      },
    });
    if (!tokenResponse.ok) {
      throw new Error(await tokenResponse.text());
    }
    const payload = await tokenResponse.json();
    apiKey = payload.api_key;
    if (!apiKey) {
      throw new Error("Response did not include api_key.");
    }
    console.log("3. Permanent API token endpoint works.");
  } catch (error) {
    console.error(`3. API token retrieval failed: ${error.message}`);
    process.exit(1);
  }

  try {
    const projectsResponse = await fetch(`${baseUrl}/api/projects/`, {
      headers: {
        Authorization: `Token ${apiKey}`,
      },
    });
    if (!projectsResponse.ok) {
      throw new Error(await projectsResponse.text());
    }
    const payload = await projectsResponse.json();
    console.log(`4. Project API access works with permanent token auth (${countProjects(payload)} visible project(s)).`);
  } catch (error) {
    console.error(`4. Project listing failed: ${error.message}`);
    process.exit(1);
  }

  try {
    const nodesResponse = await fetch(`${baseUrl}/api/processingnodes/`, {
      headers: {
        Authorization: `Token ${apiKey}`,
      },
    });
    if (!nodesResponse.ok) {
      throw new Error(await nodesResponse.text());
    }
    const payload = await nodesResponse.json();
    const onlineNodes = Array.isArray(payload) ? payload.filter((node) => node.online) : [];
    console.log(`5. Processing node API works (${onlineNodes.length} online node(s)).`);
  } catch (error) {
    console.error(`5. Processing node check failed: ${error.message}`);
    process.exit(1);
  }

  try {
    const optionsResponse = await fetch(`${baseUrl}/api/processingnodes/options/`, {
      headers: {
        Authorization: `Token ${apiKey}`,
      },
    });
    if (!optionsResponse.ok) {
      throw new Error(await optionsResponse.text());
    }
    const payload = await optionsResponse.json();
    console.log(`6. Shared processing options API works (${Array.isArray(payload) ? payload.length : 0} option(s)).`);
  } catch (error) {
    console.error(`6. Processing option check failed: ${error.message}`);
    process.exit(1);
  }

  console.log();
  console.log("All checks passed.");
  console.log();
  console.log("Use this Claude Desktop block after adjusting the path and inserting your permanent API key:");
  console.log(
    JSON.stringify(
      {
        mcpServers: {
          webodm: {
            command: "node",
            args: ["<absolute-path-to-WebODM>/mcp/webodm-mcp-server/index.js"],
            env: {
              WEBODM_BASE_URL: baseUrl,
              WEBODM_API_KEY: "paste_permanent_api_key_here",
            },
          },
        },
      },
      null,
      2
    )
  );
}

main()
  .catch((error) => {
    console.error(`Fatal error: ${error.message}`);
    process.exitCode = 1;
  })
  .finally(() => {
    rl.close();
  });
