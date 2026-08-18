#!/bin/bash
# Start Tavily API Key Pool Dashboard
# Usage: ./run_dashboard.sh [port]
PORT=${1:-8000}
uvicorn dashboard:app --host 0.0.0.0 --port "$PORT"
