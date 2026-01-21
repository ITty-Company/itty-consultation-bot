#!/usr/bin/env bash
# One-time setup script for Ubuntu/Debian VPS.
# Copies systemd unit, creates venv, installs deps, enables service.
set -euo pipefail

APP_NAME="chat-bot"
APP_DIR="/opt/${APP_NAME}"
APP_USER="chatbot"
SERVICE_NAME="chat-bot"

echo "[1/7] Installing OS packages..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

echo "[2/7] Creating user '${APP_USER}' (if missing)..."
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  sudo useradd -r -m -s /usr/sbin/nologin "${APP_USER}"
fi

echo "[3/7] Creating app directory '${APP_DIR}'..."
sudo mkdir -p "${APP_DIR}"
sudo chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo
echo "Now copy your project files into: ${APP_DIR}"
echo "You can use scp/rsync, or upload via SFTP."
echo "Then ensure ${APP_DIR}/.env exists (copy from env.example)."
echo
read -r -p "Press Enter when files are in place..."

echo "[4/7] Creating venv..."
sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/venv"
sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install -U pip

echo "[5/7] Installing Python dependencies..."
sudo -u "${APP_USER}" "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "[6/7] Installing systemd service..."
sudo cp "${APP_DIR}/deploy/bot.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo sed -i "s|/opt/chat-bot|${APP_DIR}|g" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo sed -i "s|User=chatbot|User=${APP_USER}|g" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo sed -i "s|Group=chatbot|Group=${APP_USER}|g" "/etc/systemd/system/${SERVICE_NAME}.service"

echo "[7/7] Enabling and starting service..."
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}"

echo
echo "Done."
echo "Status: sudo systemctl status ${SERVICE_NAME} --no-pager"
echo "Logs:   sudo journalctl -u ${SERVICE_NAME} -f"

