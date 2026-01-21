# GOOGLE SHEETS SETUP

Интеграция с Google Sheets **опциональная**. Если она не нужна — оставьте `USE_GOOGLE_SHEETS=false`.

## 1) Создайте Service Account и скачайте credentials

1. Откройте Google Cloud Console и создайте проект.
2. Включите API: **Google Sheets API**.
3. Создайте **Service Account** и скачайте JSON-ключ (обычно файл называется `credentials.json`).

## 2) Дайте доступ сервисному аккаунту к таблице

1. Откройте вашу таблицу Google Sheets.
2. Нажмите “Поделиться”.
3. Добавьте email сервисного аккаунта (из JSON) с правами редактора.

## 3) Разместите credentials на сервере

Рекомендуется положить файл на VPS рядом с проектом, например:

- `/opt/chat-bot/credentials.json`

и указать абсолютный путь в `.env`:

```env
USE_GOOGLE_SHEETS=true
GOOGLE_SHEET_ID=ваш_spreadsheet_id
GOOGLE_SHEET_NAME=Sheet1
GOOGLE_CREDENTIALS_FILE=/opt/chat-bot/credentials.json
```

## 4) Проверьте логи

Если всё ок — в логах при запуске будет `Google Sheets initialized: True`.
Если нет — будет предупреждение, что `credentials.json` не найден или нет доступа к таблице.

