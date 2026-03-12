#!/usr/bin/env node

import fs from "fs";
import path from "path";
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

function propertyBlock(parameter) {
  const lines = [
    `      ${parameter.name}: {`,
    `        type: "${parameter.type}",`,
    `        description: "${parameter.description}",`,
  ];

  if (parameter.enumValues.length > 0) {
    lines.push(`        enum: [${parameter.enumValues.map((value) => `"${value}"`).join(", ")}],`);
  }
  if (parameter.type === "object") {
    lines.push("        additionalProperties: true,");
  }
  if (parameter.type === "array") {
    lines.push("        items: { type: \"string\" },");
  }

  lines.push("      }");
  return lines.join("\n");
}

function buildSchemaSnippet(toolName, description, parameters) {
  const required = parameters.filter((parameter) => parameter.required).map((parameter) => `"${parameter.name}"`);
  return `  {\n    name: "${toolName}",\n    description: "${description}",\n    inputSchema: schema(\n      {\n${parameters.map(propertyBlock).join(",\n")}\n      },\n      [${required.join(", ")}]\n    ),\n  },`;
}

function buildHandlerSnippet(toolName, endpoint, method, parameters, responseMode) {
  const queryParameters = parameters.filter((parameter) => !endpoint.includes(`{${parameter.name}}`) && method === "GET");
  const bodyParameters = parameters.filter((parameter) => !endpoint.includes(`{${parameter.name}}`) && method !== "GET");
  const endpointExpression = endpoint.includes("{")
    ? `\`${endpoint.replace(/{([a-zA-Z0-9_]+)}/g, "${args.$1}")}\``
    : `"${endpoint}"`;

  const lines = [
    `  async ${toolName}(args) {`,
    "    ensureTokenAvailable();",
    `    const endpoint = ${endpointExpression};`,
  ];

  if (method === "GET") {
    if (queryParameters.length > 0) {
      lines.push("    return requestJson(endpoint, {");
      lines.push("      query: {");
      for (const parameter of queryParameters) {
        lines.push(`        ${parameter.name}: args.${parameter.name},`);
      }
      lines.push("      },");
      lines.push(`      responseType: \"${responseMode}\",`);
      lines.push("    });");
    } else {
      lines.push(`    return requestJson(endpoint, { responseType: \"${responseMode}\" });`);
    }
  } else {
    lines.push("    return requestJson(endpoint, {");
    lines.push(`      method: \"${method}\",`);
    if (bodyParameters.length > 0) {
      lines.push("      json: {");
      for (const parameter of bodyParameters) {
        lines.push(`        ${parameter.name}: args.${parameter.name},`);
      }
      lines.push("      },");
    }
    lines.push("    });");
  }

  lines.push("  },");
  return lines.join("\n");
}

async function main() {
  console.log("WebODM MCP Tool Generator");
  console.log();

  const rawName = await ask("Tool suffix (example: get_project_stats): ");
  if (!rawName.trim()) {
    throw new Error("Tool suffix is required.");
  }

  const toolName = `webodm_${rawName.trim()}`;
  const description = await ask("Description: ");
  const endpoint = await ask("Endpoint (example: /api/projects/{project_id}/stats/): ");
  const method = (await ask("HTTP method [GET]: ")).trim().toUpperCase() || "GET";
  const responseMode = (await ask("Response type [json] (json/text/auto): ")).trim().toLowerCase() || "json";

  const parameters = [];
  console.log();
  console.log("Define parameters. Leave the name blank when done.");

  while (true) {
    const name = (await ask("Parameter name: ")).trim();
    if (!name) {
      break;
    }

    const type = (await ask("Type [string] (string/number/boolean/object/array): ")).trim().toLowerCase() || "string";
    const parameterDescription = await ask("Description: ");
    const required = ((await ask("Required? [n] (y/n): ")).trim().toLowerCase() || "n") === "y";
    const enumRaw = (await ask("Enum values (comma separated, blank for none): ")).trim();

    parameters.push({
      name,
      type,
      description: parameterDescription,
      required,
      enumValues: enumRaw ? enumRaw.split(",").map((value) => value.trim()).filter(Boolean) : [],
    });
  }

  const schemaSnippet = buildSchemaSnippet(toolName, description, parameters);
  const handlerSnippet = buildHandlerSnippet(toolName, endpoint, method, parameters, responseMode);

  console.log();
  console.log("Add this to TOOL_DEFINITIONS:");
  console.log("------------------------------------------------------------");
  console.log(schemaSnippet);
  console.log("------------------------------------------------------------");
  console.log();
  console.log("Add this to TOOL_HANDLERS:");
  console.log("------------------------------------------------------------");
  console.log(handlerSnippet);
  console.log("------------------------------------------------------------");

  const save = ((await ask("Save snippets to generated/<tool>.md? [y] (y/n): ")).trim().toLowerCase() || "y") === "y";
  if (save) {
    const generatedDir = path.join(process.cwd(), "generated");
    fs.mkdirSync(generatedDir, { recursive: true });
    const outputPath = path.join(generatedDir, `${toolName}.md`);
    const content = [
      `# ${toolName}`,
      "",
      "## TOOL_DEFINITIONS",
      "```js",
      schemaSnippet,
      "```",
      "",
      "## TOOL_HANDLERS",
      "```js",
      handlerSnippet,
      "```",
      "",
      "## Notes",
      "- Update API_MAPPING.md.",
      "- Add an example to EXAMPLES.md if this tool is user-facing.",
      "- Run npm run smoke and npm test after wiring it in.",
    ].join("\n");
    fs.writeFileSync(outputPath, content, "utf8");
    console.log(`Saved ${outputPath}`);
  }
}

main()
  .catch((error) => {
    console.error(`Error: ${error.message}`);
    process.exitCode = 1;
  })
  .finally(() => {
    rl.close();
  });
