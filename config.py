import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота от @BotFather
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# ID администратора (можно получить у @userinfobot)
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# ID консультанта для получения заявок (можно получить у @userinfobot)
# Если не указан, заявки будут отправляться админу
CONSULTANT_ID = int(os.getenv('CONSULTANT_ID', '0')) if os.getenv('CONSULTANT_ID') else None
# Username консультанта для кнопки "Связаться с консультантом" (например: @consultant_username)
CONSULTANT_USERNAME = os.getenv('CONSULTANT_USERNAME', '@consultant')

# Путь к файлу с данными
DATA_FILE = 'bookings.json'

# Настройки компании (можно изменить под вашу компанию)
COMPANY_NAME = os.getenv('COMPANY_NAME', 'ITty Company')
COMPANY_DESCRIPTION = os.getenv('COMPANY_DESCRIPTION', 'Професійні IT-консультації та рішення')

# Типи консультацій (можна налаштувати)
CONSULTATION_TYPES = [
    '💼 Загальна консультація',
    '🔧 Технічна підтримка',
    '💻 Розробка проекту',
    '🔍 Аудит системи',
    '📚 Навчання',
    '🚀 Стратегічне планування',
    '🛡️ Кібербезпека',
    '☁️ Хмарні рішення'
]

# Налаштування AI-асистента
# Якщо використовуєте DeepSeek API, додайте ключ в .env
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
# Або OpenAI API
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
USE_AI_API = os.getenv('USE_AI_API', 'false').lower() == 'true'

# Налаштування Google Sheets
# ID таблицы Google (можно получить из URL: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit)
# Для таблицы: https://docs.google.com/spreadsheets/d/1xl6KQyM--IqJ8OyRV90ww1sj9AsfTZ9ZItfNEij80U0/edit
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '1xl6KQyM--IqJ8OyRV90ww1sj9AsfTZ9ZItfNEij80U0')
# Имя листа в таблице (по умолчанию 'Sheet1' - первый лист в таблице)
GOOGLE_SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME', 'Sheet1')
# Путь к JSON файлу с credentials для Google API (скачайте из Google Cloud Console)
GOOGLE_CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
USE_GOOGLE_SHEETS = os.getenv('USE_GOOGLE_SHEETS', 'false').lower() == 'true'

