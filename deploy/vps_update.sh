#!/usr/bin/env bash
# Update dependencies and restart service (run on VPS).
set -euo pipefail

APP_NAME="chat-bot"
APP_DIR="/opt/${APP_NAME}"
APP_USER="chatbot"
SERVICE_NAME="chat-bot"

echo "[1/3] Installing/Updating dependencies..."
sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "[2/3] Restarting service..."
sudo systemctl restart "${SERVICE_NAME}"

echo "[3/3] Tail logs..."
sudo journalctl -u "${SERVICE_NAME}" -n 100 --no-pager

