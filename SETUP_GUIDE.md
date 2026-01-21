# SETUP GUIDE

Короткий гайд по запуску бота локально и на сервере.

## Локально (macOS / Linux / Windows)

1. Установите Python 3.10+
2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Создайте `.env` (скопируйте из `env.example`) и заполните минимум:

```env
BOT_TOKEN=...
ADMIN_ID=...
```

4. Запуск:

```bash
python3 bot.py
```

## VPS (Ubuntu/Debian) — автозапуск 24/7 через systemd

В папке `deploy/` лежат:
- `deploy/bot.service` — systemd unit (шаблон)
- `deploy/vps_install.sh` — скрипт первичной установки
- `deploy/vps_update.sh` — скрипт обновления зависимостей и рестарта

Рекомендуемый путь приложения на VPS: `/opt/chat-bot`.

