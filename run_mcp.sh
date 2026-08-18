#!/bin/bash
# Start Tavily MCP server (stdio transport)
# Usage: ./run_mcp.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
"$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/mcp_server.py"
