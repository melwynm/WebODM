#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing MCP server dependencies..."
cd "${SCRIPT_DIR}"
npm install

echo
echo "Next steps:"
echo "1. Copy .env.example to .env and adjust WEBODM_BASE_URL if needed."
echo "2. Run: npm test"
echo "3. Add the example entry from claude_desktop_config.example.json to your Claude Desktop config."
