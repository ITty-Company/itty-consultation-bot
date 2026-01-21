#!/bin/bash
# Скрипт для безопасного перезапуска бота (без Conflict в Telegram)
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Перезапуск Telegram бота..."

# 1) Пытаемся остановить текущий экземпляр по PID из lock-файла
if [[ -f "bot.lock" ]]; then
  PID="$(cat bot.lock 2>/dev/null || true)"
  if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
    echo "⏹ Остановка текущего экземпляра (pid $PID)..."
    kill "$PID" 2>/dev/null || true
    # ждём до 5 секунд
    for _ in {1..25}; do
      if kill -0 "$PID" 2>/dev/null; then
        sleep 0.2
      else
        break
      fi
    done
    # если не остановился — добиваем
    if kill -0 "$PID" 2>/dev/null; then
      echo "⚠️ Не удалось остановить мягко, принудительно завершаю (pid $PID)..."
      kill -9 "$PID" 2>/dev/null || true
    fi
  fi
fi

# 2) На всякий случай убиваем все хвосты bot.py
pkill -f "bot.py" 2>/dev/null || true
sleep 0.5

echo "✅ Запускаю бота..."
exec python3 bot.py

