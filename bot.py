import logging
import os
import json
import sys
import fcntl
# type: ignore[reportMissingImports]
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters
from datetime import datetime
import config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Не логируем HTTP-запросы (в них виден BOT_TOKEN в URL)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Google Sheets (опционально)
try:
    from google_sheets import sheets_manager, SheetsManager
    # Логируем статус инициализации при запуске
    if sheets_manager.initialized:
        logger.info(f"✅ Google Sheets initialized on startup. Sheet: {sheets_manager.sheet_name}")
    else:
        logger.warning(f"⚠️ Google Sheets not initialized on startup. Check config and credentials.")
except Exception as e:
    logger.error(f"google_sheets module not available: {e}")
    class _StubSheetsManager:
        initialized = False
        def get_next_request_number(self): return 1
        def get_sheet_url(self): return None
        def add_request(self, *args, **kwargs): return False
        def get_total_rows(self): return 0
        def get_row_data(self, *args, **kwargs): return None
        def delete_row(self, *args, **kwargs): return False
        def update_row_status(self, *args, **kwargs): return False
    sheets_manager = _StubSheetsManager()

# Regex для кнопки "🏠 ..." (emoji может приходить с variation selector)
HOME_REGEX = r"^\s*🏠\ufe0f?"

# --- Single instance guard (macOS/Linux) ---
_lock_file_handle = None

def ensure_single_instance(lock_path: str = "bot.lock") -> None:
    """
    Prevent running multiple polling instances одновременно.
    Иначе Telegram вернёт Conflict: terminated by other getUpdates request.
    """
    global _lock_file_handle
    try:
        _lock_file_handle = open(lock_path, "w")
        fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
    except BlockingIOError:
        logger.error("Another bot instance is already running (lock file busy). Exiting.")
        raise SystemExit(1)
    except Exception as e:
        logger.error(f"Failed to acquire instance lock: {e}")
        raise SystemExit(1)

# Состояния для ConversationHandler
UNDERSTANDING, NICHE, IDEA, GOAL, TIMELINE, READY, READY_DESC, CONTACT_TYPE, CONTACT_INPUT = range(9)

# Переводы
T = {
    'uk': {
        'start': 'Щоб консультація була максимально корисною, я задам кілька коротких питань 👇\n\nПочнемо?',
        'yes': '✅ Так, поїхали',
        'later': '⏳ Пізніше',
        'canceled': '❌ Операцію скасовано.\n\nПовертаємось до головного меню👇',
        'menu_understand': '🔍 Зрозуміти, яке IT-рішення потрібне',
        'menu_structure': '🧠 Розкласти ідею по поличках',
        'menu_solution': '🛠 Підібрати оптимальне рішення',
        'menu_cost': '💰 Розрахувати орієнтовну вартість',
        'menu_consultation': '💼 Консультація з IT-спеціалістом',
        'menu_audit': '🔍 Аудит поточного проекту',
        'menu_development': '💻 Розробка нового проекту',
        'menu_support': '🛠 Технічна підтримка',
        'menu_optimization': '⚡ Оптимізація існуючого рішення',
        'menu_integration': '🔗 Інтеграція з додатками ITty',
        'integration_title': '🔗 Інтеграція з додатками ITty',
        'integration_intro': 'Ми завжди відкриті до співпраці з якісними брендами та сервісами! 🚀\n\nЩоб розглянути вашу пропозицію, нам потрібна інформація:',
        'integration_question_app': '📱 <b>З яким саме додатком/сервісом ви хочете інтегруватися?</b>\n\nВкажіть вашу назву додатку, платформи або сервісу.',
        'integration_question_why': '💼 <b>Чому ми повинні розглянути співпрацю з вами?</b>\n\nОпишіть, чому саме ITty Company має розглянути вашу пропозицію. Що робить ваш бренд особливим?',
        'integration_question_benefit': '✨ <b>Чому це вигідно для нас?</b>\n\nОпишіть переваги співпраці для ITty Company та наших клієнтів.',
        'integration_thanks': '✨ <b>Дякуємо!</b> Ми зафіксували вашу відповідь. Ваш запит передано консультанту ITty Company.\n\nКонсультант зв\'яжеться з вами найближчим часом, щоб обговорити деталі та запропонувати рішення.\n\n🙏 Дякуємо, що обрали нас.',
        'menu_consultant': '💬 Зв\'язатися з консультантом',
        'menu_book_consultation': '📅 Записатися на консультацію',
        'main_menu_title': '👋 Привіт! Я — цифровий IT-асистент ITty Company.',
        'main_menu_choose': 'Оберіть, що вас цікавить:',
        'consultation_start': 'Щоб консультація була максимально корисною, я задам кілька коротких питань 👇\n\nПочнемо?',
        'understanding': 'У тебе вже є розуміння, що саме ти хочеш?',
        'understanding_yes': '✅ Так, є розуміння',
        'understanding_partial': '❓ Є ідея, але не до кінця',
        'understanding_no': '❌ Ні, потрібна допомога з нуля',
        'niche': 'У якій ніші проект?',
        'niche_beauty': '💄 Beauty сфера',
        'niche_ecommerce': '🛒 E-commerce / Онлайн-магазин',
        'niche_education': '📚 Освіта',
        'niche_health': '🏥 Здоров\'я / Медицина',
        'niche_realestate': '🏠 Нерухомість',
        'niche_food': '🍔 Ресторани / Їжа',
        'niche_fitness': '💪 Фітнес / Спорт',
        'niche_finance': '💰 Фінанси / Банкінг',
        'niche_travel': '✈️ Подорожі / Туризм',
        'niche_tech': '💻 Технології / IT',
        'niche_thinking': '🤔 Ще думаю',
        'niche_other': 'Інше',
        'niche_other_text': 'Напиши свою нішу текстом:',
        'idea_intro': '🎯 Це дуже важливо — чим детальніше ти опишеш, тим краще я зможу допомогти!\n\n💭 Пиши все, що приходить на думку — навіть якщо здається неважливим.',
        'idea_questions': '<pre>✨ За чим цей сайт/проект? Яка його головна мета?\n🚀 Що саме він робить? Як він працює?\n🎨 Які основні функції та можливості?\n👥 Для кого він призначений? Хто твій клієнт?\n💪 Які проблеми він вирішує?\n💎 Що робить його особливим?</pre>',
        'idea_footer': '💭 Пиши все, що приходить на думку — навіть якщо здається неважливим. Кожна деталь має значення! 🌟',
        'goal': 'Яку головну мету має вирішити проект?',
        'goal_leads': '📈 Обробка великої кількості заявок',
        'goal_automation': '⚙️ Автоматизація та легке управління сайтом без інших спеціалістів',
        'goal_mvp': '🚀 Запуск MVP',
        'goal_scale': '📊 Масштабування свого бізнесу',
        'timeline': 'Плануєш запуск найближчим часом?',
        'timeline_urgent': '🔥 Терміново',
        'timeline_2_3': '⏳ Протягом 2–3 місяців',
        'timeline_3_5': '⏳ Протягом 3–5 місяців',
        'timeline_studying': '🧠 Поки вивчаю',
        'ready': 'Чи є вже щось готове в проекті?',
        'ready_yes': '✅ Так',
        'ready_no': '❌ Ні',
        'ready_desc': 'Опиши все, що вже готове:',
        'contact_type': 'Як з тобою краще звʼязатися?',
        'contact_phone': '📱 Номер телефону',
        'contact_email': '📧 Email',
        'contact_telegram': '💬 Telegram',
        'contact_phone_text': 'Напиши номер телефону',
        'contact_email_text': 'Напиши свій email',
        'contact_telegram_text': 'Напиши свій Telegram (наприклад: @username).',
        'contact_share': '👇 Натисни на кнопку нижче, щоб поділитися номером:',
        'contact_share_button': '📱 Поділитися номером',
        'final': '✨ <b>Дякуємо! Ми зафіксували вашу відповідь.</b> Ваш запит передано консультанту ITty Company.\n\nКонсультант зв\'яжеться з вами найближчим часом, щоб обговорити деталі та запропонувати рішення.\n\n🙏 Дякуємо, що обрали нас.',
        'admin_new_request': '📋 Нова заявка:\n\n',
        'admin_user': '👤 Користувач',
        'admin_understanding': '📝 Розуміння',
        'admin_niche': '🏢 Ніша',
        'admin_idea': '💡 Ідея',
        'admin_goal': '🎯 Мета',
        'admin_timeline': '⏰ Сроки',
        'admin_ready': '✅ Готово',
        'admin_contact': '📞 Контакт',
        'admin_no_username': 'без username',
        'welcome': '👋 Ласкаво просимо до ITty Company',
        'back_to_menu': '🏠 Повернутися до головного меню',
        'lang': 'Оберіть мову / Выберите язык:',
        'lang_select_text': '/ Будь ласка, оберіть мову\n/ Пожалуйста, выберите язык\n/ Please choose a language\n/ Kies een taal',
        'lang_uk': '🇺🇦 Українська',
        'lang_ru': '🇷🇺 Русский',
        'lang_en': '🇬🇧 English',
        'lang_nl': '🇳🇱 Nederlands',
        'support_title': '🛠 Технічна підтримка',
        'support_description': 'Ми завжди готові допомогти! Якщо у вас виникли питання, проблеми або потрібна допомога, зверніться до нашого адміністратора. Він швидко відповість та допоможе вирішити будь-які технічні питання! 💪',
        'support_admin_contact': '👤 <b>Контакти адміністратора:</b>',
        'support_questions': '💬 <b>Оберіть тему вашого питання:</b>',
        'support_question_site': '🌐 Сайт/додаток не працює',
        'support_question_setup': '⚙️ Допомога з налаштуванням',
        'support_question_access': '🔐 Проблеми з входом/доступом',
        'support_question_data': '💾 Втрата або відновлення даних',
        'support_question_other': '❓ Інше питання',
        'support_prompt_site': 'Опишіть, що саме не працює: де і коли зʼявляється помилка, як ви її виявили, що робили перед цим. Якщо є тексти помилок — вкажіть їх.',
        'support_prompt_setup': 'Вкажіть, з якими налаштуваннями потрібна допомога, що вже налаштовано і на якому кроці виникла проблема.',
        'support_prompt_access': 'Опишіть проблему зі входом/доступом: що саме відбувається, які повідомлення бачите, коли це почалося. Якщо пробували відновлення — напишіть.',
        'support_prompt_data': 'Розкажіть, що сталося і які дані зникли: де вони зберігалися, коли ви це помітили та як це сталося.',
        'support_prompt_other': 'Опишіть своє питання якомога детальніше.',
        'support_write_admin': '✍️ Написати адміністратору',
        'support_contact_title': '👤 <b>Контакт консультанта</b>',
        'support_contact_text': 'Ви можете звʼязатися з консультантом і детально описати свою ситуацію.\nВін допоможе та підкаже рішення.',
        'support_contact_phone_label': '📱 Telegram / телефон',
        'support_detail_thanks': '✅ <b>Дякуємо!</b> Ми передали ваш запит консультанту. Він зв\'яжеться з вами найближчим часом.\n\n📱 Telegram / телефон: <b>+380994810289</b>',
        'consultant_contact_title': '👤 <b>Контакт консультанта</b>',
        'consultant_contact_text': 'Ви можете зв\'язатися з консультантом і детально описати свою ситуацію.\nВін допоможе та підкаже рішення.',
        'consultant_contact_phone_label': '📱 Telegram / телефон',
        'support_back': '🔙 Повернутися до меню'
    },
    'ru': {
        'start': 'Чтобы консультация была максимально полезной, я задам несколько коротких вопросов 👇\n\nНачнем?',
        'yes': '✅ Да, поехали',
        'later': '⏳ Позже',
        'canceled': '❌ Операцию отменено.\n\nВозвращаемся в главное меню👇',
        'menu_understand': '🔍 Понять, какое IT-решение нужно',
        'menu_structure': '🧠 Разложить идею по полочкам',
        'menu_solution': '🛠 Подобрать оптимальное решение',
        'menu_cost': '💰 Рассчитать ориентировочную стоимость',
        'menu_consultation': '💼 Консультация с IT-специалистом',
        'menu_audit': '🔍 Аудит текущего проекта',
        'menu_development': '💻 Разработка нового проекта',
        'menu_support': '🛠 Техническая поддержка',
        'menu_optimization': '⚡ Оптимизация существующего решения',
        'menu_integration': '🔗 Интеграция с приложениями ITty',
        'integration_title': '🔗 Интеграция с приложениями ITty',
        'integration_intro': 'Мы всегда открыты к сотрудничеству с качественными брендами и сервисами! 🚀\n\nЧтобы рассмотреть ваше предложение, нам нужна информация:',
        'integration_question_app': '📱 <b>С каким именно приложением/сервисом вы хотите интегрироваться?</b>\n\nУкажите ваше название приложения, платформы или сервиса.',
        'integration_question_why': '💼 <b>Почему мы должны рассмотреть сотрудничество с вами?</b>\n\nОпишите, почему именно ITty Company должна рассмотреть ваше предложение. Что делает ваш бренд особенным?',
        'integration_question_benefit': '✨ <b>Почему это выгодно для нас?</b>\n\nОпишите преимущества сотрудничества для ITty Company и наших клиентов.',
        'integration_thanks': '✨ <b>Спасибо!</b> Мы зафиксировали ваш ответ. Ваш запрос передан консультанту ITty Company.\n\nКонсультант свяжется с вами в ближайшее время, чтобы обсудить детали и предложить решение.\n\n🙏 Спасибо, что выбрали нас.',
        'menu_consultant': '💬 Связаться с консультантом',
        'menu_book_consultation': '📅 Записаться на консультацию',
        'main_menu_title': '👋 Привет! Я — цифровой IT-ассистент ITty Company.',
        'main_menu_choose': 'Выберите, что вас интересует:',
        'consultation_start': 'Чтобы консультация была максимально полезной, я задам несколько коротких вопросов 👇\n\nНачнем?',
        'understanding': 'У тебя уже есть понимание, что именно ты хочешь?',
        'understanding_yes': '✅ Да, есть понимание',
        'understanding_partial': '❓ Есть идея, но не до конца',
        'understanding_no': '❌ Нет, нужна помощь с нуля',
        'niche': 'В какой нише проект?',
        'niche_beauty': '💄 Beauty сфера',
        'niche_ecommerce': '🛒 E-commerce / Онлайн-магазин',
        'niche_education': '📚 Образование',
        'niche_health': '🏥 Здоровье / Медицина',
        'niche_realestate': '🏠 Недвижимость',
        'niche_food': '🍔 Рестораны / Еда',
        'niche_fitness': '💪 Фитнес / Спорт',
        'niche_finance': '💰 Финансы / Банкинг',
        'niche_travel': '✈️ Путешествия / Туризм',
        'niche_tech': '💻 Технологии / IT',
        'niche_thinking': '🤔 Еще думаю',
        'niche_other': 'Другое',
        'niche_startup': '🚀 Для стартапа',
        'niche_app': '📱 Для приложения / сервиса',
        'niche_personal': '👤 Для себя',
        'niche_other_text': 'Напиши свою нишу текстом:',
        'idea_intro': '🎯 Это очень важно — чем детальнее ты опишешь, тем лучше я смогу помочь!\n\n💭 Пиши все, что приходит на ум — даже если кажется неважным.',
        'idea_questions': '<pre>✨ Зачем этот сайт/проект? Какая его главная цель?\n🚀 Что именно он делает? Как он работает?\n🎨 Какие основные функции и возможности?\n👥 Для кого он предназначен? Кто твой клиент?\n💪 Какие проблемы он решает?\n💎 Что делает его особенным?</pre>',
        'idea_footer': '💭 Пиши все, что приходит на ум — даже если кажется неважным. Каждая деталь имеет значение! 🌟',
        'goal': 'Какую главную цель должен решить проект?',
        'goal_leads': '📈 Обработка большого количества заявок',
        'goal_automation': '⚙️ Автоматизация и легкое управление сайтом без других специалистов',
        'goal_mvp': '🚀 Запуск MVP',
        'goal_scale': '📊 Масштабирование своего бизнеса',
        'timeline': 'Планируешь запуск в ближайшее время?',
        'timeline_urgent': '🔥 Срочно',
        'timeline_2_3': '⏳ В течение 2–3 месяцев',
        'timeline_3_5': '⏳ В течение 3–5 месяцев',
        'timeline_studying': '🧠 Пока изучаю',
        'ready': 'Есть ли уже что-то готовое в проекте?',
        'ready_yes': '✅ Да',
        'ready_no': '❌ Нет',
        'ready_desc': 'Опиши все, что уже готово:',
        'contact_type': 'Как с тобой лучше связаться?',
        'contact_phone': '📱 Номер телефона',
        'contact_email': '📧 Email',
        'contact_telegram': '💬 Telegram',
        'contact_phone_text': 'Напиши номер телефона',
        'contact_email_text': 'Напиши свой email',
        'contact_telegram_text': 'Напиши свой Telegram (например: @username).',
        'contact_share': '👇 Нажми на кнопку ниже, чтобы поделиться номером:',
        'contact_share_button': '📱 Поделиться номером',
        'final': '✨ <b>Спасибо! Мы зафиксировали ваш ответ.</b> Ваш запрос передан консультанту ITty Company.\n\nКонсультант свяжется с вами в ближайшее время, чтобы обсудить детали и предложить решение.\n\n🙏 Спасибо, что выбрали нас.',
        'admin_new_request': '📋 Новая заявка:\n\n',
        'admin_user': '👤 Пользователь',
        'admin_understanding': '📝 Понимание',
        'admin_niche': '🏢 Ниша',
        'admin_idea': '💡 Идея',
        'admin_goal': '🎯 Цель',
        'admin_timeline': '⏰ Сроки',
        'admin_ready': '✅ Готово',
        'admin_contact': '📞 Контакт',
        'admin_no_username': 'без username',
        'welcome': '👋 Добро пожаловать в ITty Company',
        'back_to_menu': '🏠 Вернуться в главное меню',
        'lang': 'Выберите язык:',
        'lang_select_text': '/ Будь ласка, оберіть мову\n/ Пожалуйста, выберите язык\n/ Please choose a language\n/ Kies een taal',
        'lang_uk': '🇺🇦 Украинский',
        'lang_ru': '🇷🇺 Русский',
        'lang_en': '🇬🇧 English',
        'lang_nl': '🇳🇱 Nederlands',
        'support_title': '🛠 Техническая поддержка',
        'support_description': 'Мы всегда готовы помочь! Если у вас возникли вопросы, проблемы или нужна помощь, обратитесь к нашему администратору. Он быстро ответит и поможет решить любые технические вопросы! 💪',
        'support_admin_contact': '👤 <b>Контакты администратора:</b>',
        'support_questions': '💬 <b>Выберите тему вашего вопроса:</b>',
        'support_question_site': '🌐 Сайт/приложение не работает',
        'support_question_setup': '⚙️ Помощь с настройкой',
        'support_question_access': '🔐 Проблемы со входом/доступом',
        'support_question_data': '💾 Потеря или восстановление данных',
        'support_question_other': '❓ Другой вопрос',
        'support_prompt_site': 'Опишите, что именно не работает: где и когда появляется ошибка, как вы ее обнаружили, что делали перед этим. Если есть тексты ошибок — укажите их.',
        'support_prompt_setup': 'Укажите, с какими настройками нужна помощь, что уже настроено и на каком шаге возникла проблема.',
        'support_prompt_access': 'Опишите проблему со входом/доступом: что именно происходит, какие сообщения видите, когда это началось. Если пробовали восстановление — напишите.',
        'support_prompt_data': 'Расскажите, что произошло и какие данные пропали: где они хранились, когда вы это заметили и как это случилось.',
        'support_prompt_other': 'Опишите свой вопрос как можно детальнее.',
        'support_write_admin': '✍️ Написать администратору',
        'support_contact_title': '👤 <b>Контакт консультанта</b>',
        'support_contact_text': 'Вы можете связаться с консультантом и детально описать свою ситуацию.\nОн поможет и подскажет решение.',
        'support_contact_phone_label': '📱 Telegram / телефон',
        'support_detail_thanks': '✅ <b>Спасибо!</b> Мы передали ваш запрос консультанту. Он свяжется с вами в ближайшее время.\n\n📱 Telegram / телефон: <b>+380994810289</b>',
        'consultant_contact_title': '👤 <b>Контакт консультанта</b>',
        'consultant_contact_text': 'Вы можете связаться с консультантом и детально описать свою ситуацию.\nОн поможет и подскажет решение.',
        'consultant_contact_phone_label': '📱 Telegram / телефон',
        'support_back': '🔙 Вернуться в меню'
    },
    'en': {
        'start': 'To make the consultation as useful as possible, I will ask a few short questions 👇\n\nShall we start?',
        'yes': '✅ Yes, let\'s go',
        'later': '⏳ Later',
        'canceled': '❌ Operation canceled.\n\nReturning to main menu👇',
        'menu_understand': '🔍 Understand what IT solution is needed',
        'menu_structure': '🧠 Organize the idea',
        'menu_solution': '🛠 Find the optimal solution',
        'menu_cost': '💰 Calculate approximate cost',
        'menu_consultation': '💼 Consultation with IT specialist',
        'menu_audit': '🔍 Audit of current project',
        'menu_development': '💻 Development of new project',
        'menu_support': '🛠 Technical support',
        'menu_optimization': '⚡ Optimization of existing solution',
        'menu_integration': '🔗 Integration with ITty applications',
        'integration_title': '🔗 Integration with ITty applications',
        'integration_intro': 'We are always open to cooperation with quality brands and services! 🚀\n\nTo consider your proposal, we need information:',
        'integration_question_app': '📱 <b>Which application/service do you want to integrate with?</b>\n\nSpecify your application, platform or service name.',
        'integration_question_why': '💼 <b>Why should we consider cooperation with you?</b>\n\nDescribe why ITty Company should consider your proposal. What makes your brand special?',
        'integration_question_benefit': '✨ <b>Why is this beneficial for us?</b>\n\nDescribe the benefits of cooperation for ITty Company and our clients.',
        'integration_thanks': '✨ <b>Thank you!</b> We have recorded your answer. Your request has been forwarded to the ITty Company consultant.\n\nThe consultant will contact you soon to discuss details and propose a solution.\n\n🙏 Thank you for choosing us.',
        'menu_consultant': '💬 Contact consultant',
        'menu_book_consultation': '📅 Book a consultation',
        'main_menu_title': '👋 Hello! I am a digital IT assistant of ITty Company.',
        'main_menu_choose': 'Choose what interests you:',
        'consultation_start': 'To make the consultation as useful as possible, I will ask a few short questions 👇\n\nShall we start?',
        'understanding': 'Do you already have an understanding of what exactly you want?',
        'understanding_yes': '✅ Yes, I have an understanding',
        'understanding_partial': '❓ I have an idea, but not completely',
        'understanding_no': '❌ No, I need help from scratch',
        'niche': 'What niche is the project in?',
        'niche_beauty': '💄 Beauty industry',
        'niche_ecommerce': '🛒 E-commerce / Online store',
        'niche_education': '📚 Education',
        'niche_health': '🏥 Health / Medicine',
        'niche_realestate': '🏠 Real estate',
        'niche_food': '🍔 Restaurants / Food',
        'niche_fitness': '💪 Fitness / Sports',
        'niche_finance': '💰 Finance / Banking',
        'niche_travel': '✈️ Travel / Tourism',
        'niche_tech': '💻 Technology / IT',
        'niche_thinking': '🤔 Still thinking',
        'niche_other': 'Other',
        'niche_startup': '🚀 For startup',
        'niche_app': '📱 For app / service',
        'niche_personal': '👤 For myself',
        'niche_other_text': 'Write your niche in text:',
        'idea_intro': '🎯 This is very important — the more details you provide, the better I can help!\n\n💭 Write everything that comes to mind — even if it seems unimportant.',
        'idea_questions': '<pre>✨ What is this website/project for? What is its main goal?\n🚀 What exactly does it do? How does it work?\n🎨 What are the main features and capabilities?\n👥 Who is it intended for? Who is your client?\n💪 What problems does it solve?\n💎 What makes it special?</pre>',
        'idea_footer': '💭 Write everything that comes to mind — even if it seems unimportant. Every detail matters! 🌟',
        'goal': 'What main goal should the project solve?',
        'goal_leads': '📈 Processing a large number of requests',
        'goal_automation': '⚙️ Automation and easy site management without other specialists',
        'goal_mvp': '🚀 MVP launch',
        'goal_scale': '📊 Scaling your business',
        'timeline': 'Are you planning to launch soon?',
        'timeline_urgent': '🔥 Urgent',
        'timeline_2_3': '⏳ Within 2–3 months',
        'timeline_3_5': '⏳ Within 3–5 months',
        'timeline_studying': '🧠 Still studying',
        'ready': 'Is there already something ready in the project?',
        'ready_yes': '✅ Yes',
        'ready_no': '❌ No',
        'ready_desc': 'Describe everything that is already ready:',
        'contact_type': 'How is it better to contact you?',
        'contact_phone': '📱 Phone number',
        'contact_email': '📧 Email',
        'contact_telegram': '💬 Telegram',
        'contact_phone_text': 'Write your phone number',
        'contact_email_text': 'Write your email',
        'contact_telegram_text': 'Write your Telegram (e.g. @username).',
        'contact_share': '👇 Press the button below to share your number:',
        'contact_share_button': '📱 Share number',
        'final': '✨ <b>Thank you! We have recorded your answer.</b> Your request has been forwarded to the ITty Company consultant.\n\nThe consultant will contact you soon to discuss details and suggest a solution.\n\n🙏 Thank you for choosing us.',
        'admin_new_request': '📋 New request:\n\n',
        'admin_user': '👤 User',
        'admin_understanding': '📝 Understanding',
        'admin_niche': '🏢 Niche',
        'admin_idea': '💡 Idea',
        'admin_goal': '🎯 Goal',
        'admin_timeline': '⏰ Timeline',
        'admin_ready': '✅ Ready',
        'admin_contact': '📞 Contact',
        'admin_no_username': 'no username',
        'welcome': '👋 Welcome to ITty Company',
        'back_to_menu': '🏠 Back to main menu',
        'lang': 'Choose language:',
        'lang_select_text': '/ Будь ласка, оберіть мову\n/ Пожалуйста, выберите язык\n/ Please choose a language\n/ Kies een taal',
        'lang_uk': '🇺🇦 Ukrainian',
        'lang_ru': '🇷🇺 Russian',
        'lang_en': '🇬🇧 English',
        'lang_nl': '🇳🇱 Nederlands',
        'support_title': '🛠 Technical support',
        'support_description': 'We are always ready to help! If you have questions, problems or need help, contact our administrator. He will quickly respond and help solve any technical issues! 💪',
        'support_admin_contact': '👤 <b>Administrator contacts:</b>',
        'support_questions': '💬 <b>Choose your question topic:</b>',
        'support_question_site': '🌐 Website/app is not working',
        'support_question_setup': '⚙️ Help with setup',
        'support_question_access': '🔐 Login/access issues',
        'support_question_data': '💾 Data loss or recovery',
        'support_question_other': '❓ Other question',
        'support_prompt_site': 'Describe what exactly is not working: where and when the error appears, how you discovered it, what you did before this. If there are error messages, specify them.',
        'support_prompt_setup': 'Specify which settings you need help with, what is already configured and at which step the problem occurred.',
        'support_prompt_access': 'Describe the login/access problem: what exactly happens, what messages you see, when it started. If you tried recovery, write about it.',
        'support_prompt_data': 'Tell what happened and what data was lost: where it was stored, when you noticed it and how it happened.',
        'support_prompt_other': 'Describe your question in as much detail as possible.',
        'support_write_admin': '✍️ Write to administrator',
        'support_contact_title': '👤 <b>Consultant contact</b>',
        'support_contact_text': 'You can contact the consultant and describe your situation in detail.\nThey will help and suggest a solution.',
        'support_contact_phone_label': '📱 Telegram / phone',
        'support_detail_thanks': '✅ <b>Thank you!</b> We have forwarded your request to the consultant. They will contact you soon.\n\n📱 Telegram / phone: <b>+380994810289</b>',
        'consultant_contact_title': '👤 <b>Consultant contact</b>',
        'consultant_contact_text': 'You can contact the consultant and describe your situation in detail.\nThey will help and suggest a solution.',
        'consultant_contact_phone_label': '📱 Telegram / phone',
        'support_back': '🔙 Back to menu'
    },
    'nl': {
        'start': 'Om de consultatie zo nuttig mogelijk te maken, zal ik een paar korte vragen stellen 👇\n\nZullen we beginnen?',
        'yes': '✅ Ja, laten we beginnen',
        'later': '⏳ Later',
        'canceled': '❌ Operatie geannuleerd.\n\nTerug naar hoofdmenu👇',
        'menu_understand': '🔍 Begrijpen welke IT-oplossing nodig is',
        'menu_structure': '🧠 Idee uiteenzetten',
        'menu_solution': '🛠 Optimale oplossing vinden',
        'menu_cost': '💰 Geschatte kosten berekenen',
        'menu_consultation': '💼 Consultatie met IT-specialist',
        'menu_audit': '🔍 Audit van huidig project',
        'menu_development': '💻 Ontwikkeling van nieuw project',
        'menu_support': '🛠 Technische ondersteuning',
        'menu_optimization': '⚡ Optimalisatie van bestaande oplossing',
        'menu_integration': '🔗 Integratie met ITty applicaties',
        'integration_title': '🔗 Integratie met ITty applicaties',
        'integration_intro': 'We staan altijd open voor samenwerking met kwaliteitsmerken en diensten! 🚀\n\nOm uw voorstel te overwegen, hebben we informatie nodig:',
        'integration_question_app': '📱 <b>Met welke applicatie/service wilt u integreren?</b>\n\nGeef uw applicatie-, platform- of servicenaam op.',
        'integration_question_why': '💼 <b>Waarom moeten we samenwerking met u overwegen?</b>\n\nBeschrijf waarom ITty Company uw voorstel zou moeten overwegen. Wat maakt uw merk bijzonder?',
        'integration_question_benefit': '✨ <b>Waarom is dit voordelig voor ons?</b>\n\nBeschrijf de voordelen van samenwerking voor ITty Company en onze klanten.',
        'integration_thanks': '✨ <b>Bedankt!</b> We hebben uw antwoord vastgelegd. Uw verzoek is doorgestuurd naar de ITty Company consultant.\n\nDe consultant neemt binnenkort contact met u op om de details te bespreken en een oplossing voor te stellen.\n\n🙏 Bedankt dat u voor ons heeft gekozen.',
        'menu_consultant': '💬 Contact opnemen met consultant',
        'menu_book_consultation': '📅 Consultatie boeken',
        'main_menu_title': '👋 Hallo! Ik ben een digitale IT-assistent van ITty Company.',
        'main_menu_choose': 'Kies wat u interesseert:',
        'consultation_start': 'Om de consultatie zo nuttig mogelijk te maken, zal ik een paar korte vragen stellen 👇\n\nZullen we beginnen?',
        'understanding': 'Heb je al een idee van wat je precies wilt?',
        'understanding_yes': '✅ Ja, ik heb een idee',
        'understanding_partial': '❓ Heb een idee, maar niet volledig',
        'understanding_no': '❌ Nee, heb hulp nodig vanaf nul',
        'niche': 'In welke niche is het project?',
        'niche_beauty': '💄 Beauty industrie',
        'niche_ecommerce': '🛒 E-commerce / Online winkel',
        'niche_education': '📚 Onderwijs',
        'niche_health': '🏥 Gezondheid / Geneeskunde',
        'niche_realestate': '🏠 Vastgoed',
        'niche_food': '🍔 Restaurants / Eten',
        'niche_fitness': '💪 Fitness / Sport',
        'niche_finance': '💰 Financiën / Bankieren',
        'niche_travel': '✈️ Reizen / Toerisme',
        'niche_tech': '💻 Technologie / IT',
        'niche_thinking': '🤔 Nog aan het nadenken',
        'niche_other': 'Anders',
        'niche_startup': '🚀 Voor startup',
        'niche_app': '📱 Voor app / service',
        'niche_personal': '👤 Voor mezelf',
        'niche_other_text': 'Schrijf je niche in tekst:',
        'idea_intro': '🎯 Dit is heel belangrijk — hoe meer details je geeft, hoe beter ik kan helpen!\n\n💭 Schrijf alles op wat in je opkomt — zelfs als het onbelangrijk lijkt.',
        'idea_questions': '<pre>✨ Waarvoor is deze website/project? Wat is het hoofddoel?\n🚀 Wat doet het precies? Hoe werkt het?\n🎨 Wat zijn de belangrijkste functies en mogelijkheden?\n👥 Voor wie is het bedoeld? Wie is je klant?\n💪 Welke problemen lost het op?\n💎 Wat maakt het bijzonder?</pre>',
        'idea_footer': '💭 Schrijf alles op wat in je opkomt — zelfs als het onbelangrijk lijkt. Elk detail telt! 🌟',
        'goal': 'Wat is het hoofddoel dat het project moet oplossen?',
        'goal_leads': '📈 Verwerking van een groot aantal verzoeken',
        'goal_automation': '⚙️ Automatisering en eenvoudig sitebeheer zonder andere specialisten',
        'goal_mvp': '🚀 MVP lanceren',
        'goal_scale': '📊 Schalen van uw bedrijf',
        'timeline': 'Plan je binnenkort te lanceren?',
        'timeline_urgent': '🔥 Urgent',
        'timeline_2_3': '⏳ Binnen 2–3 maanden',
        'timeline_3_5': '⏳ Binnen 3–5 maanden',
        'timeline_studying': '🧠 Nog aan het studeren',
        'ready': 'Is er al iets klaar in het project?',
        'ready_yes': '✅ Ja',
        'ready_no': '❌ Nee',
        'ready_desc': 'Beschrijf alles wat al klaar is:',
        'contact_type': 'Hoe is het beter om contact met je op te nemen?',
        'contact_phone': '📱 Telefoonnummer',
        'contact_email': '📧 Email',
        'contact_telegram': '💬 Telegram',
        'contact_phone_text': 'Schrijf je telefoonnummer',
        'contact_email_text': 'Schrijf je email',
        'contact_telegram_text': 'Schrijf je Telegram (bijv. @username).',
        'contact_share': '👇 Klik op de knop hieronder om uw nummer te delen:',
        'contact_share_button': '📱 Deel telefoonnummer',
        'final': '✨ <b>Bedankt! We hebben uw antwoord vastgelegd.</b> Uw verzoek is doorgestuurd naar de consultant van ITty Company.\n\nDe consultant neemt binnenkort contact met u op om de details te bespreken en een oplossing voor te stellen.\n\n🙏 Dank u voor uw vertrouwen.',
        'admin_new_request': '📋 Nieuw verzoek:\n\n',
        'admin_user': '👤 Gebruiker',
        'admin_understanding': '📝 Begrip',
        'admin_niche': '🏢 Niche',
        'admin_idea': '💡 Idee',
        'admin_goal': '🎯 Doel',
        'admin_timeline': '⏰ Tijdlijn',
        'admin_ready': '✅ Klaar',
        'admin_contact': '📞 Contact',
        'admin_no_username': 'geen username',
        'back_to_menu': '🏠 Terug naar hoofdmenu',
        'lang': 'Kies taal:',
        'welcome': '👋 Welkom bij ITty Company',
        'lang_select_text': '/ Будь ласка, оберіть мову\n/ Пожалуйста, выберите язык\n/ Please choose a language\n/ Kies een taal',
        'lang_uk': '🇺🇦 Oekraïens',
        'lang_ru': '🇷🇺 Russisch',
        'lang_en': '🇬🇧 Engels',
        'lang_nl': '🇳🇱 Nederlands',
        'support_title': '🛠 Technische ondersteuning',
        'support_description': 'We staan altijd klaar om te helpen! Als u vragen, problemen heeft of hulp nodig heeft, neem contact op met onze beheerder. Hij zal snel reageren en helpen bij het oplossen van technische problemen! 💪',
        'support_admin_contact': '👤 <b>Beheerder contacten:</b>',
        'support_questions': '💬 <b>Kies uw vraagonderwerp:</b>',
        'support_question_site': '🌐 Website/app werkt niet',
        'support_question_setup': '⚙️ Hulp bij configuratie',
        'support_question_access': '🔐 Inlog-/toegangsproblemen',
        'support_question_data': '💾 Gegevensverlies of herstel',
        'support_question_other': '❓ Andere vraag',
        'support_prompt_site': 'Beschrijf wat er precies niet werkt: waar en wanneer de fout verschijnt, hoe u die ontdekte en wat u deed voordat dit gebeurde. Als er foutmeldingen zijn, vermeld ze.',
        'support_prompt_setup': 'Geef aan met welke instellingen u hulp nodig heeft, wat al is ingesteld en bij welke stap het probleem optreedt.',
        'support_prompt_access': 'Beschrijf het inlog-/toegangsprobleem: wat er precies gebeurt, welke meldingen u ziet en wanneer het begon. Als u herstel hebt geprobeerd, vermeld dit.',
        'support_prompt_data': 'Leg uit wat er gebeurde en welke gegevens verloren gingen: waar ze waren opgeslagen, wanneer u het merkte en hoe het is gebeurd.',
        'support_prompt_other': 'Beschrijf uw vraag zo gedetailleerd mogelijk.',
        'support_write_admin': '✍️ Schrijf naar beheerder',
        'support_contact_title': '👤 <b>Contact met de consultant</b>',
        'support_contact_text': 'U kunt contact opnemen met de consultant en uw situatie volledig beschrijven.\nHij helpt en geeft een oplossing.',
        'support_contact_phone_label': '📱 Telegram / telefoon',
        'support_detail_thanks': '✅ <b>Bedankt!</b> We hebben uw verzoek doorgegeven aan de consultant. Hij neemt binnenkort contact met u op.\n\n📱 Telegram / telefoon: <b>+380994810289</b>',
        'consultant_contact_title': '👤 <b>Contact met de consultant</b>',
        'consultant_contact_text': 'U kunt contact opnemen met de consultant en uw situatie volledig beschrijven.\nHij helpt en geeft een oplossing.',
        'consultant_contact_phone_label': '📱 Telegram / telefoon',
        'support_back': '🔙 Terug naar menu'
    }
}

# Функции для работы с языком
def get_lang(user_id):
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            user_data = data.get(str(user_id), {})
            lang = user_data.get('lang', 'uk')
            # Убеждаемся, что язык валидный
            if lang not in ['uk', 'ru', 'en', 'nl']:
                lang = 'uk'
            return lang
    except Exception as e:
        logger.error(f"Error getting lang for user {user_id}: {e}")
        return 'uk'

def set_lang(user_id, lang):
    try:
        data = {} if not os.path.exists('users.json') else json.load(open('users.json', 'r', encoding='utf-8'))
        data[str(user_id)] = {'lang': lang, 'updated': datetime.now().isoformat()}
        json.dump(data, open('users.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    except:
        pass

def get_translations(lang):
    """Безопасно получает переводы для языка с fallback на украинский"""
    if lang not in T:
        return T['uk']  # Fallback на украинский
    return T[lang]

def get_full_text(lang, field, value):
    """Преобразует ключ в полный текст на указанном языке"""
    if not value:
        return value
    
    t = get_translations(lang)  # Используем безопасную функцию
    
    # Преобразуем ключи в полные тексты
    if field == 'understanding':
        key = f'understanding_{value}'
        return t.get(key, value)
    elif field == 'niche':
        # Если это текст (другая ниша), возвращаем как есть
        if value not in ['beauty', 'ecommerce', 'education', 'health', 'realestate', 'food', 'fitness', 'finance', 'travel', 'tech', 'thinking', 'other']:
            return value
        key = f'niche_{value}'
        return t.get(key, value)
    elif field == 'goal':
        key = f'goal_{value}'
        return t.get(key, value)
    elif field == 'timeline':
        # Заменяем подчеркивания для timeline_2_3 и timeline_3_5
        key = f'timeline_{value}'
        return t.get(key, value)
    elif field == 'ready':
        if value == 'yes':
            return t.get('ready_yes', value)
        elif value == 'no':
            return t.get('ready_no', value)
        # Если это текст описания, возвращаем как есть
        return value
    elif field == 'contact_type':
        if value == 'phone':
            return t.get('contact_phone', value)
        elif value == 'email':
            return t.get('contact_email', value)
        return value
    
    return value

# Клавиатуры
def get_lang_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(T['uk']['lang_uk'], callback_data='lang_uk')],
        [InlineKeyboardButton(T['ru']['lang_ru'], callback_data='lang_ru')],
        [InlineKeyboardButton(T.get('en', T['uk']).get('lang_en', '🇬🇧 English'), callback_data='lang_en')],
        [InlineKeyboardButton(T['nl']['lang_nl'], callback_data='lang_nl')]
    ])

def get_lang_step_photo(lang: str) -> str:
    """
    Картинка для шагов анкеты.
    Для каждого языка используем отдельный визуал вопроса про нишу.
    """
    if lang == "uk":
        return "2 укр.PNG"
    if lang == "ru":
        return "2 русский.PNG"
    if lang == "en":
        return "2 англ.jpeg"
    if lang == "nl":
        return "2 нидер.PNG"
    return "2 укр.PNG"

def get_idea_step_photo(lang: str) -> str:
    """Картинка для шага с описанием идеи проекта"""
    if lang == "uk":
        return "3 укр.PNG"
    if lang == "ru":
        return "3 русский.PNG"
    if lang == "en":
        return "3 англ.PNG"
    if lang == "nl":
        return "3 нидер.PNG"
    return "3 укр.PNG"

def get_goal_step_photo(lang: str) -> str:
    """Картинка для шага с целью бизнеса"""
    if lang == "uk":
        return "4 укр.jpeg"
    if lang == "ru":
        return "4 русский.PNG"
    if lang == "en":
        return "4 англ.PNG"
    if lang == "nl":
        return "4 нидер.PNG"
    return "4 укр.jpeg"

def get_final_step_photo() -> str:
    """Картинка для финального сообщения"""
    return "последнее.PNG"

def get_timeline_step_photo(lang: str) -> str:
    """Картинка для шага со сроками запуска"""
    if lang == "uk":
        return "5 укр.PNG"
    if lang == "ru":
        return "5 русский.PNG"
    if lang == "en":
        return "5 англ.PNG"
    if lang == "nl":
        return "5 нидер.PNG"
    return "5 укр.PNG"

def get_support_step_photo(lang: str) -> str:
    """Картинка для шага технической поддержки"""
    if lang == "uk":
        return "6 укр.PNG"
    if lang == "ru":
        return "6 русский.PNG"
    if lang == "en":
        return "6 англ.PNG"
    if lang == "nl":
        return "6 нидер.PNG"
    return "6 укр.PNG"

def get_integration_photo(lang: str) -> str:
    """Картинка для интеграции"""
    if lang == "uk":
        return "7 укр.PNG"
    if lang == "ru":
        return "7 русском.PNG"
    if lang == "en":
        return "7 англ.PNG"
    if lang == "nl":
        return "7 нидер.PNG"
    return "7 укр.PNG"

def get_welcome_photo() -> str:
    """Картинка для приветствия"""
    return "1.jpeg"

async def send_welcome_with_image(chat_id: int, text: str, bot, reply_markup=None) -> None:
    """Отправляет картинку приветствия перед текстом"""
    photo_path = get_welcome_photo()
    try:
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                await bot.send_photo(chat_id=chat_id, photo=InputFile(photo))
    except Exception as e:
        logger.error(f"Error sending welcome photo: {e}")
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

def get_back_to_menu_keyboard(lang=None, user_id=None):
    """Клавиатура с кнопкой возврата в главное меню"""
    # Если язык не передан, получаем его из user_id
    if lang is None:
        if user_id is None:
            lang = 'uk'
        else:
            lang = get_lang(user_id)
    # Убеждаемся, что язык валидный
    if lang not in ['uk', 'ru', 'en', 'nl']:
        lang = 'uk'
    
    t = get_translations(lang)
    buttons = [[KeyboardButton(t['back_to_menu'])]]
    # Кнопка "Связаться с консультантом" внизу (ReplyKeyboard) - всегда добавляем
    buttons.append([KeyboardButton(t['menu_consultant'])])
    
    # Если это администратор и Google Sheets подключен, добавляем кнопку Google Таблицы
    if user_id:
        # Проверяем, что user_id совпадает с ADMIN_ID (с учетом типов)
        is_admin = (user_id == config.ADMIN_ID) or (int(user_id) == int(config.ADMIN_ID))
        if is_admin:
            logger.debug(f"get_back_to_menu_keyboard: Admin detected: {user_id}")
            if sheets_manager.initialized:
                # Проверяем, что кнопка еще не добавлена (на всякий случай)
                has_google_button = any(
                    any("Google Таблица" in btn.text for btn in row)
                    for row in buttons
                )
                if not has_google_button:
                    buttons.append([KeyboardButton("📊 Google Таблица")])
                    logger.info(f"✅ Added Google Sheets button for admin {user_id}")
                else:
                    logger.warning(f"⚠️ Google button already exists in keyboard for admin {user_id}")
            else:
                logger.warning(f"⚠️ Admin {user_id} requested keyboard but Google Sheets not initialized (initialized={sheets_manager.initialized})")
        else:
            logger.debug(f"get_back_to_menu_keyboard: User {user_id} is not admin (ADMIN_ID={config.ADMIN_ID})")
    else:
        logger.warning(f"get_back_to_menu_keyboard: user_id is None! Keyboard created without user_id.")
    
    # Финальная проверка для администратора
    if user_id and ((user_id == config.ADMIN_ID) or (int(user_id) == int(config.ADMIN_ID))):
        final_has_button = any(
            any("Google Таблица" in btn.text for btn in row)
            for row in buttons
        )
        if sheets_manager.initialized and not final_has_button:
            logger.error(f"❌ CRITICAL: Admin keyboard missing Google button! Adding it now.")
            buttons.append([KeyboardButton("📊 Google Таблица")])
    
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def is_consultant_button_text(text: str) -> bool:
    """Проверяем, что текст соответствует кнопке 'Связаться с консультантом'"""
    if not text:
        return False
    consultant_texts = []
    for lang in ['uk', 'ru', 'en', 'nl']:
        t = get_translations(lang)
        if 'menu_consultant' in t:
            consultant_texts.append(t['menu_consultant'])
    return text in consultant_texts

class ConsultantButtonFilter(filters.MessageFilter):
    """Кастомный фильтр для кнопки консультанта"""
    def filter(self, message):
        """Проверяет, является ли сообщение кнопкой консультанта"""
        if not message or not message.text:
            return False
        return is_consultant_button_text(message.text)

# Создаем экземпляр фильтра
consultant_button_filter = ConsultantButtonFilter()

def get_main_menu_keyboard(lang='uk', user_id=None):
    """Главное меню с кнопками"""
    t = get_translations(lang)
    buttons = [
        [InlineKeyboardButton(t['menu_understand'], callback_data='menu_understand')],
        [InlineKeyboardButton(t['menu_structure'], callback_data='menu_structure')],
        [InlineKeyboardButton(t['menu_cost'], callback_data='menu_cost')],
        [InlineKeyboardButton(t['menu_consultation'], callback_data='menu_consultation')],
        [InlineKeyboardButton(t['menu_audit'], callback_data='menu_audit')],
        [InlineKeyboardButton(t['menu_support'], callback_data='menu_support')],
        [InlineKeyboardButton(t['menu_integration'], callback_data='menu_integration')]
    ]
    # Если это администратор и Google Sheets подключен, добавляем кнопку Google Таблицы
    if user_id:
        # Проверяем, что user_id совпадает с ADMIN_ID (с учетом типов)
        is_admin = (user_id == config.ADMIN_ID) or (int(user_id) == int(config.ADMIN_ID))
        if is_admin:
            if sheets_manager.initialized:
                sheet_url = sheets_manager.get_sheet_url()
                if sheet_url:
                    buttons.append([InlineKeyboardButton("📊 Google Таблица", url=sheet_url)])
                    logger.info(f"✅ Added Google Sheets button to main menu for admin {user_id}")
            else:
                logger.warning(f"⚠️ Admin {user_id} requested main menu but Google Sheets not initialized (initialized={sheets_manager.initialized})")
    return InlineKeyboardMarkup(buttons)

# Обработчики
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    context.user_data.clear()
    
    # Всегда сначала показываем приветствие на английском,
    # затем даём выбор языка отдельным сообщением.
    # Используем fallback на украинский, если английский недоступен
    welcome_text = T.get('en', T['uk']).get('welcome', T['uk']['welcome'])
    
    # Отправляем приветствие с картинкой
    await send_welcome_with_image(
        chat_id=update.message.chat_id,
        text=welcome_text,
        bot=context.bot
    )
    
    # Затем отправляем сообщение с выбором языка (на всех языках)
    await update.message.reply_text(
        T['uk']['lang_select_text'],
        reply_markup=get_lang_keyboard()
    )
    # Если /start пришёл во время активного диалога — завершаем ConversationHandler
    return ConversationHandler.END

async def handle_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор языка - показываем главное меню"""
    query = update.callback_query
    if not query:
        return
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_lang: {e}")
    
    lang_code = query.data.removeprefix('lang_')
    set_lang(query.from_user.id, lang_code)
    context.user_data.clear()
    
    lang = get_lang(query.from_user.id)
    t = get_translations(lang)
    
    # Удаляем предыдущее сообщение
    try:
        await query.delete_message()
    except:
        pass
    
    # Обновляем клавиатуру с кнопкой "Вернуться до главного меню" на выбранном языке
    # После выбора языка отправляем только текст (без картинки)
    user_id = query.from_user.id
    logger.info(f"handle_lang: User {user_id} selected language {lang_code}")
    logger.info(f"handle_lang: Is admin? {user_id == config.ADMIN_ID}")
    logger.info(f"handle_lang: Google Sheets initialized? {sheets_manager.initialized}")
    
    keyboard = get_back_to_menu_keyboard(user_id=user_id)
    keyboard_buttons = [[btn.text for btn in row] for row in keyboard.keyboard]
    logger.info(f"handle_lang: Keyboard buttons: {keyboard_buttons}")
    
    # Дополнительная проверка для администратора
    if user_id == config.ADMIN_ID:
        has_google = any("Google Таблица" in ' '.join(row) for row in keyboard_buttons)
        logger.info(f"handle_lang: Admin keyboard check - Google button present: {has_google}")
        if not has_google and sheets_manager.initialized:
            logger.error(f"handle_lang: ERROR - Admin keyboard missing Google button!")
            logger.error(f"handle_lang: user_id={user_id}, ADMIN_ID={config.ADMIN_ID}, match={user_id == config.ADMIN_ID}")
            logger.error(f"handle_lang: sheets_manager.initialized={sheets_manager.initialized}")
    
    await query.message.reply_text(
        t['main_menu_title'],
        reply_markup=keyboard
    )
    
    # Затем отправляем текст с выбором и кнопками меню
    await query.message.reply_text(
        t['main_menu_choose'],
        reply_markup=get_main_menu_keyboard(lang, user_id=user_id)
    )

async def start_consultation_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper для start_consultation - проверяет, что это не support_start_yes"""
    query = update.callback_query
    if query:
        # КРИТИЧЕСКИ ВАЖНО: проверяем ДО всего остального
        if query.data == 'support_start_yes':
            logger.error(f"❌ start_consultation_wrapper: support_start_yes should NOT be handled here! Data: {query.data}")
            # НЕ отвечаем на callback и НЕ вызываем start_consultation
            # Возвращаем END чтобы ConversationHandler не обрабатывал это
            return ConversationHandler.END
        
        # Также проверяем другие support callback'и
        if query.data.startswith('support_'):
            logger.error(f"❌ start_consultation_wrapper: support callback should NOT be handled here! Data: {query.data}")
            return ConversationHandler.END
        
        logger.info(f"start_consultation_wrapper: handling {query.data}")
    
    # Если это не support callback, вызываем обычную функцию
    return await start_consultation(update, context)

async def start_consultation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало консультации"""
    query = update.callback_query
    if query:
        
        # Гарантированно отвечаем на callback в самом начале
        try:
            await query.answer()
        except Exception as e:
            logger.error(f"Error answering callback in start_consultation: {e}")
        uid = query.from_user.id
        chat_id = query.message.chat_id
        try:
            # Сообщение с кнопкой/меню удаляем ПОСЛЕ отправки нового сообщения,
            # иначе reply на удалённое сообщение может не пройти.
            pass
        except:
            pass
    else:
        uid = update.effective_user.id
        msg_func = update.message.reply_text
    
    # Сохраняем menu_item перед очисткой, если он есть
    menu_item = context.user_data.get('menu_item', '')
    # Очищаем состояние перед началом новой консультации
    context.user_data.clear()
    # Восстанавливаем menu_item после очистки
    if menu_item:
        context.user_data['menu_item'] = menu_item
    
    lang = get_lang(uid)
    t = get_translations(lang)
    
    # Первый вопрос: понимание
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['understanding_yes'], callback_data='understanding_yes')],
        [InlineKeyboardButton(t['understanding_partial'], callback_data='understanding_partial')],
        [InlineKeyboardButton(t['understanding_no'], callback_data='understanding_no')]
    ])

    if query:
        await context.bot.send_message(chat_id=chat_id, text=t['understanding'], reply_markup=keyboard)
        try:
            await query.delete_message()
        except:
            pass
    else:
        await msg_func(t['understanding'], reply_markup=keyboard)
    return UNDERSTANDING

async def handle_understanding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа о понимании"""
    query = update.callback_query
    if not query:
        return
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_understanding: {e}")
    
    uid = query.from_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    
    understanding = query.data.removeprefix('understanding_')
    context.user_data['understanding'] = understanding
    
    # Вопрос о нише — кнопки в 2–3 колонки, чтобы все были кликабельны на любом экране
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['niche_beauty'], callback_data='niche_beauty'), InlineKeyboardButton(t['niche_ecommerce'], callback_data='niche_ecommerce'), InlineKeyboardButton(t['niche_education'], callback_data='niche_education')],
        [InlineKeyboardButton(t['niche_health'], callback_data='niche_health'), InlineKeyboardButton(t['niche_realestate'], callback_data='niche_realestate'), InlineKeyboardButton(t['niche_food'], callback_data='niche_food')],
        [InlineKeyboardButton(t['niche_fitness'], callback_data='niche_fitness'), InlineKeyboardButton(t['niche_finance'], callback_data='niche_finance'), InlineKeyboardButton(t['niche_travel'], callback_data='niche_travel')],
        [InlineKeyboardButton(t['niche_tech'], callback_data='niche_tech'), InlineKeyboardButton(t['niche_thinking'], callback_data='niche_thinking'), InlineKeyboardButton(t['niche_other'], callback_data='niche_other')]
    ])
    
    # Отправляем картинку + текст вопроса + кнопки одним сообщением.
    # Для uk/en используем отдельные визуалы, для остальных — белый фон.
    photo_path = get_lang_step_photo(lang)
    sent = False
    try:
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                await query.message.reply_photo(
                    photo=InputFile(photo),
                    caption=t['niche'],
                    reply_markup=keyboard
                )
                sent = True
    except Exception as e:
        logger.error(f"Error sending photo in handle_understanding: {e}")
        sent = False

    if not sent:
        await context.bot.send_message(chat_id=query.message.chat_id, text=t['niche'], reply_markup=keyboard)
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message in handle_understanding: {e}")
    return NICHE

async def handle_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа о нише"""
    query = update.callback_query
    if query:
        # Гарантированно отвечаем на callback в самом начале
        try:
            await query.answer()
        except Exception as e:
            logger.error(f"Error answering callback in handle_niche: {e}")
        uid = query.from_user.id
        niche_type = query.data.removeprefix('niche_')
        
        if niche_type == 'other':
            lang = get_lang(uid)
            t = get_translations(lang)
            await context.bot.send_message(chat_id=query.message.chat_id, text=t['niche_other_text'], reply_markup=get_back_to_menu_keyboard(user_id=uid))
            try:
                await query.delete_message()
            except:
                pass
            return NICHE
        
        context.user_data['niche'] = niche_type
        lang = get_lang(uid)
        t = get_translations(lang)
        
        # Вопрос об идее — отправляем картинку + текст
        idea_photo_path = get_idea_step_photo(lang)
        try:
            if os.path.exists(idea_photo_path):
                with open(idea_photo_path, 'rb') as photo:
                    await context.bot.send_photo(chat_id=query.message.chat_id, photo=InputFile(photo))
        except Exception as e:
            logger.error(f"Error sending idea photo in handle_niche: {e}")
        await context.bot.send_message(chat_id=query.message.chat_id, text=t['idea_intro'], reply_markup=get_back_to_menu_keyboard(user_id=uid))
        # Второе сообщение: вопросы (как заметка с форматированием кода)
        await context.bot.send_message(chat_id=query.message.chat_id, text=t['idea_questions'], parse_mode='HTML')
        try:
            await query.delete_message()
        except Exception:
            pass
        return IDEA
    else:
        uid = update.effective_user.id
        context.user_data['niche'] = update.message.text
        lang = get_lang(uid)
        t = get_translations(lang)
        # Держим кнопку "🏠" всегда доступной
        await update.message.reply_text("✅", reply_markup=get_back_to_menu_keyboard(user_id=uid))
        
        # Вопрос об идее — отправляем картинку + текст
        idea_photo_path = get_idea_step_photo(lang)
        try:
            if os.path.exists(idea_photo_path):
                with open(idea_photo_path, 'rb') as photo:
                    await update.message.reply_photo(photo=InputFile(photo))
        except Exception as e:
            logger.error(f"Error sending idea photo in handle_niche text: {e}")
        await update.message.reply_text(t['idea_intro'], reply_markup=get_back_to_menu_keyboard(user_id=uid))
        # Второе сообщение: вопросы (как заметка с форматированием кода)
        await update.message.reply_text(t['idea_questions'], parse_mode='HTML')
        return IDEA

async def handle_idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа об идее"""
    uid = update.effective_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    
    context.user_data['idea'] = update.message.text
    
    # Держим кнопку "🏠" всегда доступной
    await update.message.reply_text("✅", reply_markup=get_back_to_menu_keyboard(user_id=uid))
    
    # Вопрос о цели - отправляем кнопки вместе с фото
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['goal_leads'], callback_data='goal_leads')],
        [InlineKeyboardButton(t['goal_automation'], callback_data='goal_automation')],
        [InlineKeyboardButton(t['goal_mvp'], callback_data='goal_mvp')],
        [InlineKeyboardButton(t['goal_scale'], callback_data='goal_scale')]
    ])
    
    # Отправляем фото с кнопками в качестве подписи
    try:
        photo_path = get_goal_step_photo(lang)
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                await update.message.reply_photo(photo=InputFile(photo), reply_markup=keyboard)
        else:
            # Если фото нет, отправляем кнопки отдельным сообщением
            await update.message.reply_text(" ", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error sending photo with buttons in handle_idea: {e}")
        # Если ошибка при отправке фото, отправляем только кнопки
        await update.message.reply_text(" ", reply_markup=keyboard)
    
    return GOAL

async def handle_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа о цели"""
    query = update.callback_query
    if not query:
        return
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_goal: {e}")
    
    uid = query.from_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    
    goal = query.data.removeprefix('goal_')
    context.user_data['goal'] = goal
    
    # Вопрос о сроках — отправляем фото с кнопками в подписи
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['timeline_urgent'], callback_data='timeline_urgent')],
        [InlineKeyboardButton(t['timeline_2_3'], callback_data='timeline_2_3')],
        [InlineKeyboardButton(t['timeline_3_5'], callback_data='timeline_3_5')],
        [InlineKeyboardButton(t['timeline_studying'], callback_data='timeline_studying')]
    ])
    
    # Отправляем фото с кнопками в подписи
    try:
        photo_path = get_timeline_step_photo(lang)
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                await query.message.reply_photo(photo=InputFile(photo), reply_markup=keyboard)
        else:
            # Если фото нет, отправляем кнопки отдельным сообщением
            await context.bot.send_message(chat_id=query.message.chat_id, text=" ", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error sending photo with buttons in handle_goal: {e}")
        # Если ошибка при отправке фото, отправляем только кнопки
        await context.bot.send_message(chat_id=query.message.chat_id, text=" ", reply_markup=keyboard)
    
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message in handle_goal: {e}")
    return TIMELINE

async def handle_timeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа о сроках"""
    query = update.callback_query
    if not query:
        return
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_timeline: {e}")
    
    uid = query.from_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    
    # Важно: варианты типа timeline_2_3 содержат несколько "_"
    timeline = query.data.removeprefix('timeline_')
    context.user_data['timeline'] = timeline
    
    # Вопрос о готовом — сначала отправляем, потом удаляем
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['ready_yes'], callback_data='ready_yes')],
        [InlineKeyboardButton(t['ready_no'], callback_data='ready_no')]
    ])
    
    await context.bot.send_message(chat_id=query.message.chat_id, text=t['ready'], reply_markup=keyboard)
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message in handle_timeline: {e}")
    return READY

async def handle_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ответа о готовом"""
    query = update.callback_query
    if not query:
        return
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_ready: {e}")
    
    uid = query.from_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    
    ready = query.data.removeprefix('ready_')
    
    if ready == 'yes':
        context.user_data['ready'] = 'yes'
        await context.bot.send_message(chat_id=query.message.chat_id, text=t['ready_desc'], reply_markup=get_back_to_menu_keyboard(user_id=uid))
        try:
            await query.delete_message()
        except Exception as e:
            logger.error(f"Error deleting message in handle_ready: {e}")
        return READY_DESC
    else:
        context.user_data['ready'] = 'no'
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['contact_phone'], callback_data='contact_phone')],
            [InlineKeyboardButton(t['contact_email'], callback_data='contact_email')]
        ])
        # Отправляем галочку и вопрос с кнопками в одном сообщении
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ {t['contact_type']}", reply_markup=keyboard)
        try:
            await query.delete_message()
        except Exception as e:
            logger.error(f"Error deleting message in handle_ready: {e}")
        return CONTACT_TYPE

async def handle_ready_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка описания готового"""
    uid = update.effective_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    
    if not update.message or not update.message.text:
        logger.warning(f"handle_ready_desc: no message or text for user {uid}")
        return READY_DESC
    
    context.user_data['ready'] = update.message.text
    logger.info(f"handle_ready_desc: saved ready description for user {uid}, transitioning to CONTACT_TYPE")
    
    # Переходим к контакту - отправляем текст вопроса и кнопки
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['contact_phone'], callback_data='contact_phone')],
        [InlineKeyboardButton(t['contact_email'], callback_data='contact_email')]
    ])
    
    # Отправляем галочку и вопрос с кнопками в одном сообщении
    await update.message.reply_text(f"✅ {t['contact_type']}", reply_markup=keyboard)
    logger.info(f"handle_ready_desc: sent contact type question and buttons for user {uid}")
    return CONTACT_TYPE

async def handle_contact_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа контакта"""
    query = update.callback_query
    if not query:
        logger.warning("handle_contact_type called without callback_query")
        return
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
        logger.info(f"handle_contact_type: answered callback for user {query.from_user.id}, data: {query.data}")
    except Exception as e:
        logger.error(f"Error answering callback in handle_contact_type: {e}")
    
    uid = query.from_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    
    contact_type = query.data.removeprefix('contact_')
    logger.info(f"handle_contact_type: contact_type = {contact_type} for user {uid}")
    context.user_data['contact_type'] = contact_type
    
    if contact_type == 'phone':
        # Создаем клавиатуру с кнопкой для поделиться контактом и кнопкой возврата в меню
        phone_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton(t['contact_share_button'], request_contact=True)],
            [KeyboardButton(t['back_to_menu'])]
        ], resize_keyboard=True)
        # Отправляем сообщение с текстом и кнопкой для поделиться контактом
        await context.bot.send_message(chat_id=query.message.chat_id, text=t['contact_phone_text'], reply_markup=phone_keyboard)
    else:  # email
        await context.bot.send_message(chat_id=query.message.chat_id, text=t['contact_email_text'], reply_markup=get_back_to_menu_keyboard(user_id=uid))
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message in handle_contact_type: {e}")
    return CONTACT_INPUT

async def handle_contact_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода контакта"""
    uid = update.effective_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    
    # Проверяем, был ли отправлен контакт из Telegram (приоритет - контакт обрабатывается первым)
    if update.message and hasattr(update.message, 'contact') and update.message.contact:
        # Получаем номер телефона из контакта
        phone_number = update.message.contact.phone_number
        logger.info(f"Received contact from user {uid}: {phone_number}")
        context.user_data['contact'] = phone_number
    elif update.message and update.message.text:
        # Сохраняем введенный контакт (номер телефона или email)
        contact_text = update.message.text.strip()
        if not contact_text:
            await update.message.reply_text(
                t['contact_phone_text'] if context.user_data.get('contact_type') == 'phone' else t['contact_email_text'],
                reply_markup=get_back_to_menu_keyboard(user_id=uid)
            )
            return CONTACT_INPUT
        
        context.user_data['contact'] = contact_text
    else:
        logger.warning(f"Unexpected update type in handle_contact_input for user {uid}")
        return CONTACT_INPUT
    
    # Проверяем, что все обязательные поля заполнены
    required_fields = ['understanding', 'niche', 'idea', 'goal', 'timeline', 'ready', 'contact_type', 'contact']
    missing_fields = [field for field in required_fields if not context.user_data.get(field)]
    
    if missing_fields:
        logger.warning(f"Missing fields for user {uid}: {missing_fields}")
        # Если не все поля заполнены, возвращаемся к началу
        await update.message.reply_text(
            t['consultation_start'],
            reply_markup=get_back_to_menu_keyboard(user_id=uid)
        )
        return ConversationHandler.END
    
    # Отправляем данные консультанту (на русском языке с полными вопросами и ответами)
    if config.ADMIN_ID:
        try:
            admin_t = T['ru']  # Администратору всегда на русском
            
            # Получаем номер заявки
            request_number = sheets_manager.get_next_request_number() if sheets_manager.initialized else 1
            
            message = admin_t['admin_new_request']
            message += f"🔢 <b>Заявка #{request_number}</b>\n\n"
            message += f"{admin_t['admin_user']}: @{update.effective_user.username or admin_t['admin_no_username']} ({uid})\n"
            
            # Выбранная кнопка из главного меню
            menu_item = context.user_data.get('menu_item', '')
            if menu_item:
                menu_text = admin_t.get(menu_item, menu_item.replace('menu_', '').replace('_', ' ').title())
                message += f"🎯 <b>Выбранный пункт меню:</b> {menu_text}\n"
            message += "\n" + "─" * 30 + "\n\n"
            
            # Понимание - полный вопрос и ответ
            understanding_value = context.user_data.get('understanding', '')
            understanding_full = get_full_text(lang, 'understanding', understanding_value)
            message += f"❓ <b>Вопрос:</b> {admin_t.get('understanding', 'У тебя уже есть понимание, что именно ты хочешь?')}\n"
            message += f"📝 <b>Ответ:</b> {understanding_full}\n\n"
            
            # Ниша - полный вопрос и ответ
            niche_value = context.user_data.get('niche', '')
            niche_full = get_full_text(lang, 'niche', niche_value)
            message += f"❓ <b>Вопрос:</b> {admin_t.get('niche', 'В какой нише проект?')}\n"
            message += f"🏢 <b>Ответ:</b> {niche_full}\n\n"
            
            # Идея - показываем полный текст идеи пользователя
            idea_value = context.user_data.get('idea', '')
            message += f"💡 <b>Идея:</b> {idea_value if idea_value else 'Не указано'}\n\n"
            
            # Цель - полный вопрос и ответ
            goal_value = context.user_data.get('goal', '')
            goal_full = get_full_text(lang, 'goal', goal_value)
            message += f"❓ <b>Вопрос:</b> {admin_t.get('goal', 'Какую главную цель должен решить проект?')}\n"
            message += f"🎯 <b>Ответ:</b> {goal_full}\n\n"
            
            # Сроки - полный вопрос и ответ
            timeline_value = context.user_data.get('timeline', '')
            timeline_full = get_full_text(lang, 'timeline', timeline_value)
            message += f"❓ <b>Вопрос:</b> {admin_t.get('timeline', 'Планируешь запуск в ближайшее время?')}\n"
            message += f"⏰ <b>Ответ:</b> {timeline_full}\n\n"
            
            # Готово - полный вопрос и ответ
            ready_value = context.user_data.get('ready', '')
            ready_full = get_full_text(lang, 'ready', ready_value)
            message += f"❓ <b>Вопрос:</b> {admin_t.get('ready', 'Есть ли уже что-то готовое в проекте?')}\n"
            message += f"✅ <b>Ответ:</b> {ready_full}\n\n"
            
            # Контакт - полный вопрос и ответ
            contact_type_value = context.user_data.get('contact_type', '')
            contact_type_full = get_full_text(lang, 'contact_type', contact_type_value)
            contact_value = context.user_data.get('contact', '')
            message += f"❓ <b>Вопрос:</b> {admin_t.get('contact_type', 'Как с тобой лучше связаться?')}\n"
            message += f"📞 <b>Ответ:</b> {contact_type_full}: {contact_value}\n"
            
            # Создаем клавиатуру с кнопкой для открытия Google Таблицы
            keyboard = []
            if sheets_manager.initialized and sheets_manager.get_sheet_url():
                keyboard.append([InlineKeyboardButton("📊 Открыть Google Таблицу", url=sheets_manager.get_sheet_url())])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            await context.bot.send_message(
                chat_id=config.ADMIN_ID, 
                text=message, 
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
            # Преобразуем технический ключ меню в читаемый текст (имя кнопки из главного меню)
            menu_item_text = menu_item or ''
            if menu_item_text and menu_item_text.startswith('menu_'):
                # Получаем текст кнопки из переводов текущего языка пользователя
                menu_text = t.get(menu_item_text, '')
                if not menu_text or menu_text == menu_item_text:
                    # Если не нашли в текущем языке, пробуем русский
                    menu_text = T['ru'].get(menu_item_text, menu_item_text)
                menu_item_text = menu_text
            elif not menu_item_text:
                menu_item_text = '-'  # Если кнопка не выбрана, ставим прочерк
            
            # Записываем заявку в Google Sheets (всегда пытаемся записать)
            request_data = {
                'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'name': update.effective_user.first_name or '',
                'username': update.effective_user.username or '',
                'user_id': str(uid),
                'language': lang,
                'request_type': menu_item_text,  # Теперь это читаемый текст, а не технический ключ
                'project_for': '',
                'understanding': understanding_full,
                'niche': niche_full,
                'details': idea_value or '',
                'project_type': '',
                'has_ready': ready_full,
                'goal': goal_full,
                'timeline': timeline_full,
                'important': '',
                'contact_type': contact_type_full,
                'contact': contact_value,
                'status': 'Новая'
            }
            
            # Пытаемся записать в Google Sheets
            if sheets_manager.initialized:
                try:
                    success = sheets_manager.add_request(request_data)
                    if success:
                        logger.info(f"✅ Заявка пользователя {uid} успешно записана в Google Sheets")
                    else:
                        logger.warning(f"⚠️ Не удалось записать заявку пользователя {uid} в Google Sheets")
                except Exception as e:
                    logger.error(f"❌ Ошибка при записи заявки в Google Sheets: {e}", exc_info=True)
            else:
                logger.warning(f"⚠️ Google Sheets не инициализирован. Заявка пользователя {uid} не записана в таблицу.")
                logger.warning(f"Проверьте настройки: USE_GOOGLE_SHEETS={config.USE_GOOGLE_SHEETS}, файл {config.GOOGLE_CREDENTIALS_FILE} существует: {os.path.exists(config.GOOGLE_CREDENTIALS_FILE) if config.GOOGLE_CREDENTIALS_FILE else False}")
        except Exception as e:
            logger.error(f"Error sending to consultant: {e}")
    
    # Финальное сообщение (HTML для жирного заголовка) + фото
    final_photo_path = get_final_step_photo()
    try:
        if os.path.exists(final_photo_path):
            with open(final_photo_path, 'rb') as photo:
                await update.message.reply_photo(photo=InputFile(photo))
    except Exception as e:
        logger.error(f"Error sending final photo: {e}")
    await update.message.reply_text(t['final'], parse_mode='HTML')
    
    context.user_data.clear()
    return ConversationHandler.END

async def handle_google_sheet_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия кнопки Google Таблица"""
    user_id = update.effective_user.id
    
    # Проверяем, что это администратор
    if user_id != config.ADMIN_ID:
        return
    
    # Проверяем, что Google Sheets подключен
    if not sheets_manager.initialized:
        await update.message.reply_text(
            "⚠️ Google Sheets не подключен.\n\n"
            "Проверьте настройки в .env файле:\n"
            "- USE_GOOGLE_SHEETS=true\n"
            "- GOOGLE_SHEET_ID=...\n"
            "- GOOGLE_CREDENTIALS_FILE=credentials.json",
            reply_markup=get_back_to_menu_keyboard(user_id=user_id)
        )
        return
    
    sheet_url = sheets_manager.get_sheet_url()
    if sheet_url:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Открыть Google Таблицу", url=sheet_url)]
        ])
        await update.message.reply_text(
            "📊 <b>Google Таблица</b>\n\n"
            "Нажмите на кнопку ниже, чтобы открыть таблицу с заявками:",
            parse_mode='HTML',
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            "❌ Не удалось получить ссылку на Google Таблицу.",
            reply_markup=get_back_to_menu_keyboard(user_id=user_id)
        )

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    # Может быть вызвано как из MessageHandler, так и из CallbackQueryHandler
    if update.message:
        uid = update.message.from_user.id
        chat_id = update.message.chat_id
        msg_func = update.message.reply_text
    elif update.callback_query:
        query = update.callback_query
        # Гарантированно отвечаем на callback в самом начале
        try:
            await query.answer()
        except Exception as e:
            logger.error(f"Error answering callback in back_to_menu: {e}")
        uid = query.from_user.id
        chat_id = query.message.chat_id
        try:
            await query.delete_message()
        except Exception as e:
            logger.error(f"Error deleting message in back_to_menu: {e}")
        msg_func = lambda text, **kwargs: context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    else:
        return ConversationHandler.END
    
    lang = get_lang(uid)
    t = get_translations(lang)
    context.user_data.clear()
    
    # Логируем для администратора
    if uid == config.ADMIN_ID:
        logger.info(f"back_to_menu: Admin {uid} returning to menu")
        logger.info(f"back_to_menu: Google Sheets initialized: {sheets_manager.initialized}")
    
    # Показываем главное меню без картинки
    keyboard = get_back_to_menu_keyboard(user_id=uid)
    
    # Логируем клавиатуру для администратора
    if uid == config.ADMIN_ID:
        logger.info(f"back_to_menu: Keyboard buttons for admin: {[[btn.text for btn in row] for row in keyboard.keyboard]}")
    
    await msg_func(
        t['main_menu_title'],
        reply_markup=keyboard
    )
    await msg_func(
        t['main_menu_choose'],
        reply_markup=get_main_menu_keyboard(lang, user_id=uid)
    )
    return ConversationHandler.END

def is_known_callback(data: str) -> bool:
    """Проверяем, что callback относится к известным обработчикам"""
    if not data:
        return False
    known_prefixes = (
        "lang_",
        "menu_",
        "start_",
        "support_",
        "admin_",
        "contact_",
        "understanding_",
        "niche_",
        "goal_",
        "timeline_",
        "ready_",
        "help_",
        "consult_",
    )
    return data.startswith(known_prefixes)

async def handle_unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных/устаревших callback — возвращаем в меню"""
    query = update.callback_query
    if not query:
        return
    # Если callback известный — не перехватываем
    if is_known_callback(query.data):
        return
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_unknown_callback: {e}")
    # Сбрасываем состояние и показываем меню
    uid = query.from_user.id
    lang = get_lang(uid)
    t = get_translations(lang)
    context.user_data.clear()
    await query.message.reply_text(
        t['main_menu_title'],
        reply_markup=get_back_to_menu_keyboard(user_id=uid)
    )
    await query.message.reply_text(
        t['main_menu_choose'],
        reply_markup=get_main_menu_keyboard(lang, user_id=uid)
    )
    try:
        await query.delete_message()
    except Exception:
        pass

async def start_later(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Позже - показываем главное меню"""
    query = update.callback_query
    if not query:
        return
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in start_later: {e}")
    context.user_data.clear()
    
    lang = get_lang(query.from_user.id)
    t = get_translations(lang)
    
    try:
        await query.delete_message()
    except:
        pass
    
    # Показываем сообщение об отмене
    await query.message.reply_text(t['canceled'])
    
    # Затем отправляем текст с выбором и кнопками меню (без приветствия)
    await query.message.reply_text(
        t['main_menu_choose'],
        reply_markup=get_main_menu_keyboard(lang, user_id=query.from_user.id)
    )

async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки Техническая поддержка - сразу показываем вопросы"""
    query = update.callback_query
    if not query:
        return
    
    # Сбрасываем ключи консультации, чтобы они не мешали поддержке
    for key in ['understanding', 'niche', 'idea', 'goal', 'timeline', 'ready', 'contact_type', 'contact']:
        context.user_data.pop(key, None)
    
    # Принимаем как новый callback, так и старые help_* (на случай старых клавиатур)
    if query.data != 'menu_support' and not query.data.startswith('help_'):
        logger.warning(f"handle_support called with wrong data: {query.data}")
        return
    
    logger.info(f"handle_support called with data: {query.data}")
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_support: {e}")
        return
    
    lang = get_lang(query.from_user.id)
    t = get_translations(lang)
    
    # Сразу показываем экран поддержки с вопросами
    await _send_support_screen(query, context)

async def _send_support_screen(query, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет экран поддержки с контактами и вопросами"""
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in _send_support_screen: {e}")
    
    lang = get_lang(query.from_user.id)
    t = get_translations(lang)
    
    # Получаем информацию об администраторе
    admin_id = config.ADMIN_ID
    admin_username = None
    
    # Пытаемся получить username администратора из бота
    try:
        if admin_id and admin_id > 0:
            admin_chat = await context.bot.get_chat(admin_id)
            admin_username = admin_chat.username
    except Exception as e:
        logger.error(f"Error getting admin username: {e}")
    
    # Сначала отправляем картинку по языку
    support_photo_path = get_support_step_photo(lang)
    try:
        if os.path.exists(support_photo_path):
            with open(support_photo_path, 'rb') as photo:
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=InputFile(photo))
    except Exception as e:
        logger.error(f"Error sending support photo: {e}")

    # Формируем сообщение с текстом (без заголовка и без лишних отступов)
    # Убираем лишние переводы строк, чтобы не было пустого промежутка
    description = t['support_description'].strip()
    questions = t['support_questions'].strip()
    # Контакты администратора не показываем в тексте, только кнопкой
    message = f"{description}\n\n{questions}"
    
    # Создаем клавиатуру с вопросами
    keyboard_buttons = []
    keyboard_buttons += [
        [InlineKeyboardButton(t['support_question_site'], callback_data='support_question_site')],
        [InlineKeyboardButton(t['support_question_setup'], callback_data='support_question_setup')],
        [InlineKeyboardButton(t['support_question_access'], callback_data='support_question_access')],
        [InlineKeyboardButton(t['support_question_data'], callback_data='support_question_data')],
        [InlineKeyboardButton(t['support_question_other'], callback_data='support_question_other')]
    ]
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    # Отправляем сообщение
    await query.message.reply_text(message, parse_mode='HTML', reply_markup=keyboard)
    
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message in _send_support_screen: {e}")

async def ignore_support_start_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Заглушка для исключения всех support callback'ов из ConversationHandler"""
    query = update.callback_query
    if query:
        data = query.data
        if data.startswith('support_') or data == 'menu_support':
            logger.warning(f"ignore_support_start_yes: ignoring support callback '{data}' in ConversationHandler")
            return ConversationHandler.END
    return ConversationHandler.END

async def ignore_support_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback для ConversationHandler - завершает диалог, если пользователь перешел в техподдержку или интеграцию, или нажал кнопку консультанта"""
    if update.message:
        # Проверяем, нажата ли кнопка консультанта - завершаем диалог, чтобы основной обработчик мог обработать её
        if is_consultant_button_text(update.message.text):
            logger.info(f"ignore_support_text_messages: Consultant button pressed, ending conversation for user {update.effective_user.id} to allow handler to process it")
            return ConversationHandler.END
        # Проверяем, ждем ли мы ввод для поддержки или интеграции
        awaiting_support = context.user_data.get('awaiting_support_details')
        awaiting_support_contact = context.user_data.get('awaiting_support_contact_input')
        awaiting_integration = context.user_data.get('awaiting_integration')
        if awaiting_support or awaiting_support_contact or awaiting_integration:
            logger.info(f"ignore_support_text_messages: Ending conversation for user {update.effective_user.id} to process support/integration. awaiting_support={awaiting_support}, awaiting_support_contact={awaiting_support_contact}, awaiting_integration={awaiting_integration}")
            return ConversationHandler.END
    return None

async def handle_support_later(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки "Позже" в разделе поддержки"""
    query = update.callback_query
    if not query:
        return
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_support_later: {e}")
    
    lang = get_lang(query.from_user.id)
    t = get_translations(lang)
    
    context.user_data.clear()
    
    try:
        await query.delete_message()
    except:
        pass
    
    # Показываем сообщение об отмене
    await query.message.reply_text(t['canceled'])
    
    # Затем отправляем текст с выбором и кнопками меню
    await query.message.reply_text(
        t['main_menu_choose'],
        reply_markup=get_main_menu_keyboard(lang, user_id=query.from_user.id)
    )

async def handle_support_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на вопрос в разделе поддержки"""
    query = update.callback_query
    if not query:
        return
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_support_question: {e}")
    
    lang = get_lang(query.from_user.id)
    t = get_translations(lang)
    
    question_type = query.data
    
    # Формируем сообщение с вопросом
    question_text = ""
    prompt_text = ""
    if question_type == 'support_question_site':
        question_text = t['support_question_site']
        prompt_text = t['support_prompt_site']
    elif question_type == 'support_question_setup':
        question_text = t['support_question_setup']
        prompt_text = t['support_prompt_setup']
    elif question_type == 'support_question_access':
        question_text = t['support_question_access']
        prompt_text = t['support_prompt_access']
    elif question_type == 'support_question_data':
        question_text = t['support_question_data']
        prompt_text = t['support_prompt_data']
    elif question_type == 'support_question_other':
        question_text = t['support_question_other']
        prompt_text = t['support_prompt_other']
    
    message = f"❓ <b>{question_text}</b>\n\n{prompt_text}"
    
    # Сохраняем тип вопроса и ждём сообщение с деталями
    context.user_data['awaiting_support_details'] = True
    context.user_data['support_question_type'] = question_type
    context.user_data['support_question_label'] = question_text
    
    logger.info(f"handle_support_question: Set awaiting_support_details=True for user {query.from_user.id}, question_type={question_type}")
    
    # Отправляем сообщение без кнопок
    await query.message.reply_text(message, parse_mode='HTML')
    
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message in handle_support_question: {e}")

async def handle_support_contact_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор способа связи для заявки в техподдержку."""
    query = update.callback_query
    if not query:
        return

    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_support_contact_type: {e}")

    uid = query.from_user.id
    lang = get_lang(uid)
    t = get_translations(lang)

    # ожидаем выбор контакта только после ввода деталей
    if not context.user_data.get("awaiting_support_contact_type"):
        return

    contact_type = query.data.removeprefix("support_contact_")
    context.user_data["support_contact_type"] = contact_type
    context.user_data.pop("awaiting_support_contact_type", None)

    if contact_type == "phone":
        phone_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton(t['contact_share_button'], request_contact=True)],
            [KeyboardButton(t['back_to_menu'])]
        ], resize_keyboard=True)
        context.user_data["awaiting_support_contact_input"] = True
        await context.bot.send_message(chat_id=query.message.chat_id, text=t["contact_phone_text"], reply_markup=phone_keyboard)
    elif contact_type == "email":
        context.user_data["awaiting_support_contact_input"] = True
        await context.bot.send_message(chat_id=query.message.chat_id, text=t["contact_email_text"], reply_markup=get_back_to_menu_keyboard(user_id=uid))
    else:
        # по запросу: только телефон или email
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Пожалуйста, выберите: 📱 Номер телефона или 📧 Email.",
            reply_markup=get_back_to_menu_keyboard(user_id=uid),
        )

    try:
        await query.delete_message()
    except Exception:
        pass

async def finalize_support_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Финализация заявки техподдержки: отправка админу + запись в Sheets."""
    # Может быть вызвано как из MessageHandler (update.message),
    # так и из CallbackQueryHandler (update.callback_query)
    uid = update.effective_user.id
    lang = get_lang(uid)
    t = get_translations(lang)

    if update.message:
        chat_id = update.message.chat_id
        reply_func = update.message.reply_text
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
        reply_func = lambda text, **kwargs: context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    else:
        # fallback
        chat_id = uid
        reply_func = lambda text, **kwargs: context.bot.send_message(chat_id=chat_id, text=text, **kwargs)

    question_type = context.user_data.get("support_question_type", "")
    question_label = context.user_data.get("support_question_label", "")
    details = context.user_data.get("support_details", "")
    contact_type = context.user_data.get("support_contact_type", "")
    contact_value = context.user_data.get("support_contact_value", "")

    # если contact_value еще не заполнен, попробуем взять из username (telegram)
    if not contact_value and update.effective_user.username and contact_type == "telegram":
        contact_value = f"@{update.effective_user.username}"

    # Сообщение админу
    if config.ADMIN_ID:
        username = update.effective_user.username or t.get('admin_no_username', 'no username')
        admin_message = (
            "🛠 <b>Новая заявка: техподдержка</b>\n\n"
            f"👤 {update.effective_user.first_name or ''} (@{username})\n"
            f"🆔 ID: {uid}\n"
            f"🌍 Язык: {lang}\n"
            f"📌 Тема: {question_label or question_type}\n\n"
            f"📝 Детали:\n{details}\n\n"
            f"☎️ Контакт: {contact_type} {contact_value}"
        )
        try:
            await context.bot.send_message(chat_id=config.ADMIN_ID, text=admin_message, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error sending support request to admin: {e}")

    # Запись в Google Sheets
    request_type = f"{t['menu_support']} - {question_label or question_type}"
    request_data = {
        'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'name': update.effective_user.first_name or '',
        'username': update.effective_user.username or '',
        'user_id': str(uid),
        'language': lang,
        'request_type': request_type,
        'project_for': '',
        'understanding': '',
        'niche': '',
        'details': details,
        'project_type': '',
        'has_ready': '',
        'goal': '',
        'timeline': '',
        'important': '',
        'contact_type': contact_type,
        'contact': contact_value,
        'status': 'Новая'
    }

    logger.info(f"finalize_support_request: Attempting to save to Google Sheets. Initialized: {sheets_manager.initialized}")
    if sheets_manager.initialized:
        try:
            success = sheets_manager.add_request(request_data)
            if success:
                logger.info(f"✅ Support request {uid} saved to Google Sheets")
            else:
                logger.warning(f"⚠️ Failed to save support request {uid} to Google Sheets. add_request returned False")
        except Exception as e:
            logger.error(f"❌ Error saving support request to Google Sheets: {e}", exc_info=True)
    else:
        logger.warning("⚠️ Google Sheets not initialized for support request.")

    # очистка состояния поддержки
    for k in [
        "awaiting_support_details",
        "awaiting_support_contact_type",
        "awaiting_support_contact_input",
        "support_question_type",
        "support_question_label",
        "support_details",
        "support_contact_type",
        "support_contact_value",
        "support_contact_type_label",
    ]:
        context.user_data.pop(k, None)

    await reply_func(
        t['support_detail_thanks'],
        parse_mode='HTML',
        reply_markup=get_back_to_menu_keyboard(user_id=uid)
    )

async def handle_support_details_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста с деталями по запросу в техподдержку"""
    logger.info(f"handle_support_details_input: called for user {update.effective_user.id if update.effective_user else 'unknown'}")
    if not update.message:
        logger.info("handle_support_details_input: no message, returning")
        return
    
    # Если это кнопка консультанта — пропускаем, пусть её обработает handle_consultant_button
    if update.message.text and is_consultant_button_text(update.message.text):
        logger.info(f"handle_support_details_input: consultant button detected, skipping")
        return
    
    # Если админ вводит команды панели — не перехватываем
    if update.effective_user.id == config.ADMIN_ID and context.user_data.get('admin_action'):
        logger.info(f"handle_support_details_input: admin action, skipping")
        return
    
    # Если ожидается интеграция — не перехватываем
    if context.user_data.get('awaiting_integration'):
        logger.info(f"handle_support_details_input: awaiting_integration, skipping")
        return
    
    # 1) Если ждём контакт после деталей — обрабатываем контакт и финализируем заявку
    if context.user_data.get("awaiting_support_contact_input"):
        uid = update.effective_user.id
        lang = get_lang(uid)
        t = get_translations(lang)
        contact_type = context.user_data.get("support_contact_type", "")

        # контакт из Telegram
        if hasattr(update.message, "contact") and update.message.contact:
            context.user_data["support_contact_value"] = update.message.contact.phone_number
        else:
            contact_text = (update.message.text or "").strip()
            if not contact_text:
                # повторяем вопрос
                if contact_type == "phone":
                    await update.message.reply_text(t["contact_phone_text"], reply_markup=get_back_to_menu_keyboard(user_id=uid))
                elif contact_type == "email":
                    await update.message.reply_text(t["contact_email_text"], reply_markup=get_back_to_menu_keyboard(user_id=uid))
                else:
                    await update.message.reply_text(t["contact_telegram_text"], reply_markup=get_back_to_menu_keyboard(user_id=uid))
                return
            context.user_data["support_contact_value"] = contact_text

        context.user_data.pop("awaiting_support_contact_input", None)
        await finalize_support_request(update, context)
        return

    # Дальше — ожидаем именно текст с деталями
    if not (update.message.text and update.message.text.strip()):
        logger.info("handle_support_details_input: no text details, returning")
        return

    # 2) Если не ждём детали — пропускаем
    if not context.user_data.get('awaiting_support_details'):
        logger.info(f"handle_support_details_input: not awaiting_support_details, skipping. user_data keys: {list(context.user_data.keys())}")
        return
    
    logger.info(f"handle_support_details_input: processing support details from user {update.effective_user.id}")
    
    lang = get_lang(update.effective_user.id)
    t = get_translations(lang)
    
    details = update.message.text.strip()
    question_type = context.user_data.get('support_question_type', '')
    question_label = context.user_data.get('support_question_label', '')

    # сохраняем детали, затем спрашиваем контакт
    context.user_data["support_details"] = details
    context.user_data["awaiting_support_details"] = False
    context.user_data["awaiting_support_contact_type"] = True

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['contact_phone'], callback_data='support_contact_phone')],
        [InlineKeyboardButton(t['contact_email'], callback_data='support_contact_email')],
    ])

    await update.message.reply_text(f"✅ {t['contact_type']}", reply_markup=keyboard)
    logger.info(f"handle_support_details_input: asked contact type for support request user {update.effective_user.id}")
    return

async def handle_integration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки Интеграция с приложениями ITty"""
    query = update.callback_query
    if not query:
        return
    
    # Сбрасываем ключи консультации, чтобы они не мешали интеграции
    for key in ['understanding', 'niche', 'idea', 'goal', 'timeline', 'ready', 'contact_type', 'contact']:
        context.user_data.pop(key, None)
    
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_integration: {e}")
    
    lang = get_lang(query.from_user.id)
    t = get_translations(lang)
    
    # Начинаем с первого вопроса
    context.user_data['awaiting_integration'] = True
    context.user_data['integration_step'] = 'app'
    context.user_data['integration_data'] = {}
    logger.info(f"handle_integration: Set awaiting_integration=True, integration_step='app' for user {query.from_user.id}")
    
    # Сначала отправляем фото интеграции
    integration_photo_path = get_integration_photo(lang)
    try:
        if os.path.exists(integration_photo_path):
            with open(integration_photo_path, 'rb') as photo:
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=InputFile(photo))
    except Exception as e:
        logger.error(f"Error sending integration photo: {e}")
    
    # Затем отправляем текст после фото
    intro_message = f"{t['integration_intro']}\n\n{t['integration_question_app']}"
    await query.message.reply_text(intro_message, parse_mode='HTML')
    logger.info(f"handle_integration: Sent intro message and question_app for user {query.from_user.id}")
    
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message in handle_integration: {e}")

async def handle_integration_contact_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор способа связи для заявки интеграции."""
    query = update.callback_query
    if not query:
        return

    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_integration_contact_type: {e}")

    uid = query.from_user.id
    lang = get_lang(uid)
    t = get_translations(lang)

    # ожидаем выбор контакта только после второго вопроса
    if context.user_data.get('integration_step') != 'contact':
        return

    contact_type = query.data.removeprefix("integration_contact_")
    context.user_data["integration_contact_type"] = contact_type
    context.user_data["awaiting_integration_contact_input"] = True

    if contact_type == "phone":
        phone_keyboard = ReplyKeyboardMarkup([
            [KeyboardButton(t['contact_share_button'], request_contact=True)],
            [KeyboardButton(t['back_to_menu'])]
        ], resize_keyboard=True)
        await context.bot.send_message(chat_id=query.message.chat_id, text=t["contact_phone_text"], reply_markup=phone_keyboard)
    elif contact_type == "email":
        await context.bot.send_message(chat_id=query.message.chat_id, text=t["contact_email_text"], reply_markup=get_back_to_menu_keyboard(user_id=uid))
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Пожалуйста, выберите: 📱 Номер телефона или 📧 Email.",
            reply_markup=get_back_to_menu_keyboard(user_id=uid),
        )

    try:
        await query.delete_message()
    except Exception:
        pass

async def handle_integration_details_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста с деталями по запросу интеграции"""
    logger.info(f"handle_integration_details_input: called for user {update.effective_user.id if update.effective_user else 'unknown'}")
    if not update.message:
        logger.info("handle_integration_details_input: no message, returning")
        return
    
    # Если это кнопка консультанта — пропускаем, пусть её обработает handle_consultant_button
    if update.message.text and is_consultant_button_text(update.message.text):
        logger.info("handle_integration_details_input: consultant button detected, skipping")
        return
    
    # Если админ вводит команды панели — не перехватываем
    if update.effective_user.id == config.ADMIN_ID and context.user_data.get('admin_action'):
        logger.info("handle_integration_details_input: admin action, skipping")
        return
    
    # Если пользователь ожидает детали техподдержки — не перехватываем
    if context.user_data.get('awaiting_support_details'):
        logger.info("handle_integration_details_input: awaiting_support_details, skipping")
        return
    
    if not context.user_data.get('awaiting_integration'):
        logger.info(f"handle_integration_details_input: not awaiting_integration, skipping. user_data keys: {list(context.user_data.keys())}")
        return
    
    logger.info(f"handle_integration_details_input: processing integration input for user {update.effective_user.id}")
    
    lang = get_lang(update.effective_user.id)
    t = get_translations(lang)
    
    step = context.user_data.get('integration_step', 'app')
    integration_data = context.user_data.get('integration_data', {})
    
    # Если ждём ввод контакта
    if context.user_data.get("awaiting_integration_contact_input"):
        uid = update.effective_user.id
        contact_type = context.user_data.get("integration_contact_type", "")
        
        # контакт из Telegram
        if hasattr(update.message, "contact") and update.message.contact:
            contact_text = update.message.contact.phone_number
        else:
            if not update.message.text:
                logger.info("handle_integration_details_input: awaiting contact but no text/contact, returning")
                return
            contact_text = update.message.text.strip()
            if not contact_text:
                # повторяем вопрос
                if contact_type == "phone":
                    await update.message.reply_text(t["contact_phone_text"], reply_markup=get_back_to_menu_keyboard(user_id=uid))
                elif contact_type == "email":
                    await update.message.reply_text(t["contact_email_text"], reply_markup=get_back_to_menu_keyboard(user_id=uid))
                return
        
        # Обрабатываем контакт
        integration_data['contact'] = contact_text
        context.user_data['integration_data'] = integration_data
        context.user_data.pop("awaiting_integration_contact_input", None)
        
        # Отправляем администратору
        if config.ADMIN_ID:
            username = update.effective_user.username or t.get('admin_no_username', 'no username')
            contact_type_label = "Телефон" if contact_type == "phone" else "Email"
            admin_message = (
                "🔗 <b>Новая заявка: Интеграция с приложениями ITty</b>\n\n"
                f"👤 {update.effective_user.first_name or ''} (@{username})\n"
                f"🆔 ID: {update.effective_user.id}\n"
                f"🌍 Язык: {lang}\n\n"
                f"📱 <b>Приложение/сервис:</b>\n{integration_data.get('app', '')}\n\n"
                f"💼 <b>Почему должны сотрудничать:</b>\n{integration_data.get('why', '')}\n\n"
                f"📞 <b>Контакт ({contact_type_label}):</b>\n{contact_text}"
            )
            try:
                await context.bot.send_message(
                    chat_id=config.ADMIN_ID,
                    text=admin_message,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error sending integration request to admin: {e}")
        
        # Запись в Google Sheets
        request_data = {
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'name': update.effective_user.first_name or '',
            'username': update.effective_user.username or '',
            'user_id': str(update.effective_user.id),
            'language': lang,
            'request_type': t['menu_integration'],
            'project_for': '',
            'understanding': '',
            'niche': '',
            'details': f"Приложение: {integration_data.get('app', '')}\n\nПочему сотрудничать: {integration_data.get('why', '')}",
            'project_type': '',
            'has_ready': '',
            'goal': '',
            'timeline': '',
            'important': '',
            'contact_type': contact_type_label,
            'contact': contact_text,
            'status': 'Новая'
        }
        
        if sheets_manager.initialized:
            try:
                success = sheets_manager.add_request(request_data)
                if success:
                    logger.info(f"✅ Integration request {update.effective_user.id} saved to Google Sheets")
                else:
                    logger.warning(f"⚠️ Failed to save integration request {update.effective_user.id} to Google Sheets")
            except Exception as e:
                logger.error(f"❌ Error saving integration request to Google Sheets: {e}", exc_info=True)
        else:
            logger.warning("⚠️ Google Sheets not initialized for integration request.")
        
        # Очищаем данные
        context.user_data.pop('awaiting_integration', None)
        context.user_data.pop('integration_step', None)
        context.user_data.pop('integration_data', None)
        context.user_data.pop('integration_contact_type', None)
        
        # Отправляем финальное сообщение с благодарностью
        await update.message.reply_text(t['integration_thanks'], parse_mode='HTML')
        return
    
    # Проверяем текст только если не ждем контакт
    if not context.user_data.get("awaiting_integration_contact_input"):
        if not update.message.text:
            logger.info("handle_integration_details_input: no text and not awaiting contact, returning")
            return
        text = update.message.text.strip()
    else:
        # Если ждем контакт, текст может быть пустым (если это контакт из Telegram)
        text = update.message.text.strip() if update.message.text else ""
    
    if step == 'app':
        logger.info(f"handle_integration_details_input: processing step 'app' for user {update.effective_user.id}, text: {text[:50]}")
        integration_data['app'] = text
        context.user_data['integration_step'] = 'why'
        context.user_data['integration_data'] = integration_data
        logger.info(f"handle_integration_details_input: set integration_step='why', sending question_why")
        await update.message.reply_text(t['integration_question_why'], parse_mode='HTML')
        logger.info(f"handle_integration_details_input: sent question_why for user {update.effective_user.id}")
    elif step == 'why':
        integration_data['why'] = text
        context.user_data['integration_step'] = 'contact'
        context.user_data['integration_data'] = integration_data
        
        # Спрашиваем способ связи
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(t['contact_phone'], callback_data='integration_contact_phone')],
            [InlineKeyboardButton(t['contact_email'], callback_data='integration_contact_email')],
        ])
        
        await update.message.reply_text(f"✅ {t['contact_type']}", reply_markup=keyboard)
        logger.info(f"handle_integration_details_input: asked contact type for integration request user {update.effective_user.id}")
        return
    elif step == 'contact':
        # Пользователь ввёл контакт текстом (без нажатия кнопки) — принимаем как Telegram/текст
        contact_text = text
        contact_type_label = "Telegram/текст"
        integration_data['contact'] = contact_text
        context.user_data['integration_data'] = integration_data
        context.user_data.pop("awaiting_integration", None)
        context.user_data.pop("integration_step", None)
        context.user_data.pop("integration_contact_type", None)
        context.user_data.pop("awaiting_integration_contact_input", None)
        
        # Отправляем администратору
        if config.ADMIN_ID:
            username = update.effective_user.username or t.get('admin_no_username', 'no username')
            admin_message = (
                "🔗 <b>Новая заявка: Интеграция с приложениями ITty</b>\n\n"
                f"👤 {update.effective_user.first_name or ''} (@{username})\n"
                f"🆔 ID: {update.effective_user.id}\n"
                f"🌍 Язык: {lang}\n\n"
                f"📱 <b>Приложение/сервис:</b>\n{integration_data.get('app', '')}\n\n"
                f"💼 <b>Почему должны сотрудничать:</b>\n{integration_data.get('why', '')}\n\n"
                f"📞 <b>Контакт ({contact_type_label}):</b>\n{contact_text}"
            )
            try:
                await context.bot.send_message(
                    chat_id=config.ADMIN_ID,
                    text=admin_message,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error sending integration request to admin: {e}")
        
        # Запись в Google Sheets
        request_data = {
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'name': update.effective_user.first_name or '',
            'username': update.effective_user.username or '',
            'user_id': str(update.effective_user.id),
            'language': lang,
            'request_type': t['menu_integration'],
            'project_for': '',
            'understanding': '',
            'niche': '',
            'details': f"Приложение: {integration_data.get('app', '')}\n\nПочему сотрудничать: {integration_data.get('why', '')}",
            'project_type': '',
            'has_ready': '',
            'goal': '',
            'timeline': '',
            'important': '',
            'contact_type': contact_type_label,
            'contact': contact_text,
            'status': 'Новая'
        }
        
        if sheets_manager.initialized:
            try:
                success = sheets_manager.add_request(request_data)
                if success:
                    logger.info(f"✅ Integration request {update.effective_user.id} saved to Google Sheets")
                else:
                    logger.warning(f"⚠️ Failed to save integration request {update.effective_user.id} to Google Sheets")
            except Exception as e:
                logger.error(f"❌ Error saving integration request to Google Sheets: {e}", exc_info=True)
        else:
            logger.warning("⚠️ Google Sheets not initialized for integration request.")
        
        await update.message.reply_text(t['integration_thanks'], parse_mode='HTML')
        return

async def route_support_integration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ЕДИНЫЙ роутер для свободного ввода (support/integration/admin).
    Нужен, чтобы MessageHandler'ы не конфликтовали из‑за порядка регистрации.
    """
    if not update.message:
        return

    uid = update.effective_user.id if update.effective_user else None

    # Админский ввод (удаление/обновление строк) — даём приоритет
    if uid == config.ADMIN_ID and context.user_data.get("admin_action"):
        return await handle_admin_input(update, context)

    # Кнопка консультанта — не трогаем (её обрабатывает отдельный handler выше)
    if update.message.text and is_consultant_button_text(update.message.text):
        return

    # Если активна интеграция — отправляем в интеграцию
    if context.user_data.get("awaiting_integration") or \
       context.user_data.get("awaiting_integration_contact_input") or \
       context.user_data.get("integration_step") in {"app", "why", "contact"}:
        return await handle_integration_details_input(update, context)

    # Если активна техподдержка — отправляем в поддержку
    if context.user_data.get("awaiting_support_details") or \
       context.user_data.get("awaiting_support_contact_input") or \
       context.user_data.get("awaiting_support_contact_type"):
        return await handle_support_details_input(update, context)

    # Иначе — ничего не делаем (пусть обработают другие специфичные хендлеры ниже, если есть)
    return

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок главного меню"""
    query = update.callback_query
    if not query:
        return
    
    # Перенаправляем menu_support напрямую, чтобы не зависеть от порядка обработчиков
    if query.data == 'menu_support':
        return await handle_support(update, context)
    # Перенаправляем menu_integration
    if query.data == 'menu_integration':
        return await handle_integration(update, context)
    # Поддержка старых callback_data help_* (если пользователь нажал старую кнопку)
    if query.data.startswith('help_'):
        return await handle_support(update, context)
    # menu_book_consultation обрабатывается ConversationHandler
    if query.data == 'menu_book_consultation':
        return
    
    logger.info(f"handle_menu called with data: {query.data}")
    
    # Гарантированно отвечаем на callback в самом начале
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback in handle_menu: {e}")
    
    lang = get_lang(query.from_user.id)
    t = get_translations(lang)
    
    # Сохраняем выбранный пункт меню
    menu_item = query.data
    
    # Очищаем состояние перед началом новой консультации
    context.user_data.clear()
    # Сохраняем menu_item после очистки
    context.user_data['menu_item'] = menu_item
    
    # Показываем сообщение "Щоб консультація була максимально корисною..." с кнопками
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t['yes'], callback_data='start_yes')],
        [InlineKeyboardButton(t['later'], callback_data='start_later')]
    ])
    
    # Сначала отправляем новое сообщение с кнопками, потом удаляем старое
    # (так надійніше — кнопки вже в чаті до видалення повідомлення)
    await query.message.reply_text(t['consultation_start'], reply_markup=keyboard)
    
    try:
        await query.delete_message()
    except Exception as e:
        logger.error(f"Error deleting message in handle_menu: {e}")

# Команды для администратора
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status - проверка статуса Google Sheets"""
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    
    status_msg = f"📊 <b>Статус Google Sheets</b>\n\n"
    status_msg += f"✅ Инициализирован: {sheets_manager.initialized}\n"
    
    if sheets_manager.initialized:
        status_msg += f"📄 Sheet ID: {sheets_manager.sheet_id}\n"
        status_msg += f"📋 Sheet Name: {sheets_manager.sheet_name}\n"
        status_msg += f"🔗 URL: {sheets_manager.get_sheet_url()}\n"
        status_msg += f"📊 Всего строк: {sheets_manager.get_total_rows()}\n"
        status_msg += f"🔢 Следующий номер: {sheets_manager.get_next_request_number()}\n\n"
        
        # Проверяем клавиатуру
        keyboard = get_back_to_menu_keyboard(user_id=user_id)
        has_google_button = any(
            any("Google Таблица" in btn.text for btn in row)
            for row in keyboard.keyboard
        )
        status_msg += f"🔘 Кнопка в клавиатуре: {'✅ Да' if has_google_button else '❌ Нет'}\n\n"
        
        if has_google_button:
            status_msg += "✅ <b>Кнопка должна быть видна в меню!</b>\n"
            status_msg += "Если не видите кнопку, отправьте /refresh для обновления клавиатуры."
        else:
            status_msg += "⚠️ <b>Кнопка не найдена в клавиатуре!</b>\n"
            status_msg += "Отправьте /refresh для обновления."
    else:
        status_msg += "\n⚠️ Google Sheets не инициализирован!\n"
        status_msg += "Проверьте настройки и перезапустите бота."
    
    await update.message.reply_text(
        status_msg,
        parse_mode='HTML',
        reply_markup=get_back_to_menu_keyboard(user_id=user_id)
    )

async def sheettest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /sheettest - тестовая запись в Google Sheets (только админ)."""
    user_id = update.effective_user.id
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return

    if not getattr(sheets_manager, "initialized", False):
        await update.message.reply_text(
            "⚠️ Google Sheets не инициализирован — запись невозможна.\n\n"
            "Проверьте `/status` и логи при запуске.",
            parse_mode="Markdown",
            reply_markup=get_back_to_menu_keyboard(user_id=user_id),
        )
        return

    test_data = {
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "name": "Admin test",
        "username": update.effective_user.username or "",
        "user_id": str(user_id),
        "language": get_lang(user_id),
        "request_type": "🧪 /sheettest",
        "project_for": "",
        "understanding": "TEST",
        "niche": "TEST",
        "details": "Test row from /sheettest",
        "project_type": "",
        "has_ready": "TEST",
        "goal": "TEST",
        "timeline": "TEST",
        "important": "",
        "contact_type": "Telegram",
        "contact": f"@{update.effective_user.username}" if update.effective_user.username else "",
        "status": "Новая",
    }

    ok = False
    err = None
    try:
        ok = bool(sheets_manager.add_request(test_data))
    except Exception as e:
        err = str(e)

    # После записи попробуем прочитать общее кол-во строк (это покажет, что читаем правильный лист)
    total_rows = None
    try:
        total_rows = sheets_manager.get_total_rows()
    except Exception:
        total_rows = None

    msg = "🧪 <b>/sheettest</b>\n\n"
    msg += f"Инициализирован: <b>{'Да' if sheets_manager.initialized else 'Нет'}</b>\n"
    msg += f"Лист: <b>{getattr(sheets_manager, 'sheet_name', '')}</b>\n"
    msg += f"Запись: <b>{'✅ УСПЕХ' if ok else '❌ НЕ УДАЛОСЬ'}</b>\n"
    if total_rows is not None:
        msg += f"Всего строк сейчас: <b>{total_rows}</b>\n"
    if err:
        msg += f"\nОшибка: <code>{err}</code>\n"

    await update.message.reply_text(
        msg,
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard(user_id=user_id),
    )

async def test_keyboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test - тестовая команда для проверки клавиатуры"""
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    
    # Создаем клавиатуру напрямую
    keyboard = get_back_to_menu_keyboard(user_id=user_id)
    
    # Логируем все детали
    logger.info(f"test_keyboard_command: User ID: {user_id}")
    logger.info(f"test_keyboard_command: ADMIN_ID: {config.ADMIN_ID}")
    logger.info(f"test_keyboard_command: Match: {user_id == config.ADMIN_ID}")
    logger.info(f"test_keyboard_command: Sheets initialized: {sheets_manager.initialized}")
    logger.info(f"test_keyboard_command: Keyboard rows: {len(keyboard.keyboard)}")
    for i, row in enumerate(keyboard.keyboard, 1):
        buttons = [btn.text for btn in row]
        logger.info(f"test_keyboard_command: Row {i}: {buttons}")
        if 'Google Таблица' in ' '.join(buttons):
            logger.info(f"test_keyboard_command: ✅ Google button found in row {i}!")
    
    # Отправляем сообщение с клавиатурой
    await update.message.reply_text(
        f"🧪 <b>Тест клавиатуры</b>\n\n"
        f"Ваш ID: {user_id}\n"
        f"ADMIN_ID: {config.ADMIN_ID}\n"
        f"Совпадает: {'✅ Да' if user_id == config.ADMIN_ID else '❌ Нет'}\n"
        f"Google Sheets: {'✅ Инициализирован' if sheets_manager.initialized else '❌ Нет'}\n"
        f"Кнопок в клавиатуре: {len(keyboard.keyboard)}\n\n"
        f"<b>Кнопка Google Таблица должна быть видна ниже!</b>",
        parse_mode='HTML',
        reply_markup=keyboard
    )

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /refresh - обновление клавиатуры для администратора"""
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    
    lang = get_lang(user_id)
    t = get_translations(lang)
    
    # Создаем новую клавиатуру
    keyboard = get_back_to_menu_keyboard(user_id=user_id)
    has_google_button = any(
        any("Google Таблица" in btn.text for btn in row)
        for row in keyboard.keyboard
    )
    
    logger.info(f"refresh_command: Admin {user_id} requested keyboard refresh")
    logger.info(f"refresh_command: Google Sheets initialized: {sheets_manager.initialized}")
    logger.info(f"refresh_command: Keyboard has Google button: {has_google_button}")
    logger.info(f"refresh_command: Keyboard buttons: {[[btn.text for btn in row] for row in keyboard.keyboard]}")
    
    # Устанавливаем клавиатуру по умолчанию для этого пользователя
    try:
        # type: ignore[reportMissingImports]
        from telegram import BotCommand
        # Устанавливаем команды бота
        commands = [
            BotCommand("start", "Главное меню"),
            BotCommand("admin", "Панель администратора"),
            BotCommand("status", "Статус Google Sheets"),
            BotCommand("refresh", "Обновить клавиатуру")
        ]
        await context.bot.set_my_commands(commands)
    except Exception as e:
        logger.error(f"Error setting bot commands: {e}")
    
    # Сначала удаляем старую клавиатуру, отправляя сообщение с пустой клавиатурой
    try:
        # type: ignore[reportMissingImports]
        from telegram import ReplyKeyboardRemove
        await update.message.reply_text(
            "🔄 Обновляю клавиатуру...",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        logger.error(f"Error removing old keyboard: {e}")
    
    # Отправляем сообщение с новой клавиатурой
    # Используем reply_markup для принудительного обновления
    msg = (
        f"🔄 <b>Клавиатура обновлена</b>\n\n"
        f"Статус Google Sheets: {'✅ Инициализирован' if sheets_manager.initialized else '❌ Не инициализирован'}\n"
        f"Кнопка Google Таблица: {'✅ Добавлена' if has_google_button else '❌ Не добавлена'}\n\n"
    )
    
    if has_google_button:
        msg += "✅ <b>Кнопка должна быть видна ниже!</b>\n\n"
        msg += "Если кнопка не появилась, попробуйте:\n"
        msg += "1. Отправить /start и выбрать язык заново\n"
        msg += "2. Нажать кнопку '🏠 Вернуться в главное меню'"
    else:
        msg += "⚠️ <b>Кнопка не добавлена!</b>\n\n"
        msg += "Проверьте:\n"
        msg += f"1. Google Sheets инициализирован: {sheets_manager.initialized}\n"
        msg += f"2. Ваш ID совпадает с ADMIN_ID: {user_id == config.ADMIN_ID}\n"
        msg += "3. Бот был перезапущен после установки библиотек"
    
    # Отправляем новую клавиатуру
    await update.message.reply_text(
        msg,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    
    # Также отправляем главное меню для полного обновления
    await update.message.reply_text(
        t['main_menu_choose'],
        reply_markup=get_main_menu_keyboard(lang, user_id=user_id)
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /admin - панель управления для администратора"""
    user_id = update.effective_user.id
    
    if user_id != config.ADMIN_ID:
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    
    # Проверяем статус Google Sheets
    logger.info(f"Admin {user_id} requested /admin command")
    logger.info(f"Google Sheets initialized: {sheets_manager.initialized}")
    
    if not sheets_manager.initialized:
        await update.message.reply_text(
            "⚠️ Google Sheets не подключен.\n\n"
            "Проверьте настройки в .env файле:\n"
            "- USE_GOOGLE_SHEETS=true\n"
            "- GOOGLE_SHEET_ID=...\n"
            "- GOOGLE_CREDENTIALS_FILE=credentials.json\n\n"
            "Также убедитесь, что библиотеки установлены:\n"
            "pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client",
            reply_markup=get_back_to_menu_keyboard(user_id=user_id)
        )
        return
    
    sheet_url = sheets_manager.get_sheet_url()
    total_rows = sheets_manager.get_total_rows()
    total_requests = max(0, total_rows - 1)  # Минус заголовок
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Открыть Google Таблицу", url=sheet_url)],
        [InlineKeyboardButton("📋 Показать статистику", callback_data="admin_stats")],
        [InlineKeyboardButton("🗑️ Удалить строку", callback_data="admin_delete")],
        [InlineKeyboardButton("🔄 Обновить статус", callback_data="admin_status")]
    ])
    
    message = (
        "👑 <b>Панель администратора</b>\n\n"
        f"📊 Всего заявок: <b>{total_requests}</b>\n"
        f"📄 Всего строк в таблице: <b>{total_rows}</b>\n\n"
        "Выберите действие:"
    )
    
    await update.message.reply_text(message, parse_mode='HTML', reply_markup=keyboard)

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику по заявкам"""
    query = update.callback_query
    if not query:
        return
    
    if query.from_user.id != config.ADMIN_ID:
        await query.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    await query.answer()
    
    if not sheets_manager.initialized:
        await query.message.reply_text("⚠️ Google Sheets не подключен.")
        return
    
    total_rows = sheets_manager.get_total_rows()
    total_requests = max(0, total_rows - 1)
    
    # Получаем последние 5 заявок
    recent_requests = []
    if total_rows > 1:
        for i in range(max(2, total_rows - 4), total_rows + 1):
            row_data = sheets_manager.get_row_data(i)
            if row_data and len(row_data) > 0:
                request_num = row_data[0] if len(row_data) > 0 else str(i - 1)
                username = row_data[3] if len(row_data) > 3 else "N/A"
                date = row_data[1] if len(row_data) > 1 else "N/A"
                status = row_data[18] if len(row_data) > 18 else "Новая"
                recent_requests.append(f"#{request_num} | @{username} | {date} | {status}")
    
    message = (
        f"📊 <b>Статистика заявок</b>\n\n"
        f"📈 Всего заявок: <b>{total_requests}</b>\n\n"
    )
    
    if recent_requests:
        message += "📋 <b>Последние 5 заявок:</b>\n"
        for req in recent_requests:
            message += f"• {req}\n"
    else:
        message += "📭 Заявок пока нет."
    
    sheet_url = sheets_manager.get_sheet_url()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Открыть Google Таблицу", url=sheet_url)],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ])
    
    await query.message.reply_text(message, parse_mode='HTML', reply_markup=keyboard)

async def admin_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос номера строки для удаления"""
    query = update.callback_query
    if not query:
        return
    
    if query.from_user.id != config.ADMIN_ID:
        await query.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    await query.answer()
    
    total_rows = sheets_manager.get_total_rows()
    
    message = (
        f"🗑️ <b>Удаление строки</b>\n\n"
        f"Всего строк в таблице: <b>{total_rows}</b>\n"
        f"Доступные номера строк: <b>2-{total_rows}</b>\n\n"
        "Введите номер строки для удаления:\n"
        "<i>Например: 5</i>"
    )
    
    context.user_data['admin_action'] = 'delete'
    
    await query.message.reply_text(message, parse_mode='HTML')

async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос номера строки и статуса для обновления"""
    query = update.callback_query
    if not query:
        return
    
    if query.from_user.id != config.ADMIN_ID:
        await query.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    await query.answer()
    
    total_rows = sheets_manager.get_total_rows()
    
    message = (
        f"🔄 <b>Обновление статуса</b>\n\n"
        f"Всего строк в таблице: <b>{total_rows}</b>\n"
        f"Доступные номера строк: <b>2-{total_rows}</b>\n\n"
        "Введите номер строки и новый статус в формате:\n"
        "<i>Например: 5 В работе</i>\n"
        "<i>Или: 5 Завершено</i>"
    )
    
    context.user_data['admin_action'] = 'status'
    
    await query.message.reply_text(message, parse_mode='HTML')

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню администратора"""
    query = update.callback_query
    if not query:
        return
    
    if query.from_user.id != config.ADMIN_ID:
        await query.answer("❌ У вас нет доступа", show_alert=True)
        return
    
    await query.answer()
    
    sheet_url = sheets_manager.get_sheet_url()
    total_rows = sheets_manager.get_total_rows()
    total_requests = max(0, total_rows - 1)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Открыть Google Таблицу", url=sheet_url)],
        [InlineKeyboardButton("📋 Показать статистику", callback_data="admin_stats")],
        [InlineKeyboardButton("🗑️ Удалить строку", callback_data="admin_delete")],
        [InlineKeyboardButton("🔄 Обновить статус", callback_data="admin_status")]
    ])
    
    message = (
        "👑 <b>Панель администратора</b>\n\n"
        f"📊 Всего заявок: <b>{total_requests}</b>\n"
        f"📄 Всего строк в таблице: <b>{total_rows}</b>\n\n"
        "Выберите действие:"
    )
    
    await query.message.edit_text(message, parse_mode='HTML', reply_markup=keyboard)

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода администратора для удаления/обновления строк"""
    user_id = update.effective_user.id
    
    # Проверяем, что это администратор и есть активное действие
    if user_id != config.ADMIN_ID:
        return
    
    # Если ожидается техподдержка или интеграция — не перехватываем
    if context.user_data.get('awaiting_support_details') or context.user_data.get('awaiting_integration'):
        return
    
    action = context.user_data.get('admin_action')
    if not action:
        return  # Если нет активного действия, игнорируем
    
    text = update.message.text.strip()
    
    if action == 'delete':
        try:
            row_number = int(text)
            if sheets_manager.delete_row(row_number):
                await update.message.reply_text(
                    f"✅ Строка {row_number} успешно удалена!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 В панель администратора", callback_data="admin_back")]
                    ])
                )
            else:
                await update.message.reply_text(
                    f"❌ Не удалось удалить строку {row_number}.\n"
                    f"Проверьте, что номер строки корректен (от 2 до {sheets_manager.get_total_rows()})"
                )
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите корректный номер строки (число).")
        finally:
            context.user_data.pop('admin_action', None)
    
    elif action == 'status':
        try:
            parts = text.split(' ', 1)
            if len(parts) < 2:
                await update.message.reply_text(
                    "❌ Неверный формат. Используйте: <номер строки> <новый статус>\n"
                    "Например: 5 В работе"
                )
                return
            
            row_number = int(parts[0])
            new_status = parts[1]
            
            if sheets_manager.update_row_status(row_number, new_status):
                await update.message.reply_text(
                    f"✅ Статус строки {row_number} обновлен на '{new_status}'!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 В панель администратора", callback_data="admin_back")]
                    ])
                )
            else:
                await update.message.reply_text(
                    f"❌ Не удалось обновить статус строки {row_number}.\n"
                    f"Проверьте, что номер строки корректен (от 2 до {sheets_manager.get_total_rows()})"
                )
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите корректный номер строки (число).")
        finally:
            context.user_data.pop('admin_action', None)

async def handle_consultant_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопки 'Связаться с консультантом' из reply-клавиатуры"""
    logger.info(f"handle_consultant_button: called for user {update.effective_user.id if update.effective_user else 'unknown'}")
    if not update.message or not update.message.text:
        logger.info("handle_consultant_button: no message or text, returning")
        return
    
    # Проверяем, что это действительно кнопка консультанта (на любом языке)
    if not is_consultant_button_text(update.message.text):
        logger.info(f"handle_consultant_button: not consultant button text: '{update.message.text}', returning")
        return
    
    logger.info(f"handle_consultant_button: processing consultant button for user {update.effective_user.id}")
    
    # Очищаем состояние консультации, если оно было активно
    context.user_data.clear()
    
    # Получаем язык пользователя и отправляем сообщение на его языке
    lang = get_lang(update.effective_user.id)
    t = get_translations(lang)
    phone = "+380994810289"
    message = (
        f"{t['consultant_contact_title']}\n\n"
        f"{t['consultant_contact_text']}\n\n"
        f"{t['consultant_contact_phone_label']}: <b>{phone}</b>"
    )
    await update.message.reply_text(message, parse_mode='HTML')
    logger.info(f"handle_consultant_button: sent message to user {update.effective_user.id}")

def main():
    """Запуск бота"""
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return

    ensure_single_instance()
    
    # Проверяем статус Google Sheets при запуске
    logger.info("=" * 50)
    logger.info("🤖 Запуск бота...")
    logger.info(f"👤 ADMIN_ID: {config.ADMIN_ID}")
    if hasattr(sheets_manager, 'initialized'):
        logger.info(f"📊 Google Sheets initialized: {sheets_manager.initialized}")
        if sheets_manager.initialized:
            logger.info(f"📊 Sheet ID: {sheets_manager.sheet_id}")
            logger.info(f"📊 Sheet Name: {sheets_manager.sheet_name}")
            logger.info(f"📊 Sheet URL: {sheets_manager.get_sheet_url()}")
            
            # Тестируем создание клавиатуры для администратора
            test_keyboard = get_back_to_menu_keyboard(user_id=config.ADMIN_ID)
            has_button = any(
                any("Google Таблица" in btn.text for btn in row)
                for row in test_keyboard.keyboard
            )
            logger.info(f"📊 Тест клавиатуры для админа: кнопка Google Таблица {'✅ найдена' if has_button else '❌ не найдена'}")
            logger.info(f"📊 Кнопки клавиатуры: {[[btn.text for btn in row] for row in test_keyboard.keyboard]}")
        else:
            logger.warning("⚠️ Google Sheets не инициализирован! Кнопка для администратора не будет показана.")
            logger.warning("Проверьте: USE_GOOGLE_SHEETS=true, credentials.json существует, библиотеки установлены")
    logger.info("=" * 50)
    
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # ConversationHandler для консультации
    consultation_handler = ConversationHandler(
        entry_points=[
            # Паттерн должен точно совпадать только с start_yes, но не с support_start_yes
            # Используем более строгий паттерн
            CallbackQueryHandler(start_consultation_wrapper, pattern=r"^start_yes$"),
            CallbackQueryHandler(start_consultation_wrapper, pattern="^menu_book_consultation$")
        ],
        states={
            UNDERSTANDING: [
                CallbackQueryHandler(handle_understanding, pattern="^understanding_")
            ],
            NICHE: [
                CallbackQueryHandler(handle_niche, pattern="^niche_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(HOME_REGEX), handle_niche),
                MessageHandler(filters.Regex(HOME_REGEX), back_to_menu)
            ],
            IDEA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(HOME_REGEX), handle_idea),
                MessageHandler(filters.Regex(HOME_REGEX), back_to_menu)
            ],
            GOAL: [CallbackQueryHandler(handle_goal, pattern="^goal_")],
            TIMELINE: [CallbackQueryHandler(handle_timeline, pattern="^timeline_")],
            READY: [CallbackQueryHandler(handle_ready, pattern="^ready_")],
            READY_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(HOME_REGEX), handle_ready_desc),
                MessageHandler(filters.Regex(HOME_REGEX), back_to_menu)
            ],
            CONTACT_TYPE: [CallbackQueryHandler(handle_contact_type, pattern="^contact_")],
            CONTACT_INPUT: [
                MessageHandler(filters.CONTACT, handle_contact_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(HOME_REGEX), handle_contact_input),
                MessageHandler(filters.Regex(HOME_REGEX), back_to_menu)
            ]
        },
        fallbacks=[
            # Исключаем все support callback'и из ConversationHandler
            CallbackQueryHandler(ignore_support_start_yes, pattern="^support_"),
            CallbackQueryHandler(start_later, pattern="^start_later$"),
            # Завершаем диалог, если пришло текстовое сообщение или контакт, а мы ждем ввод для поддержки/интеграции
            MessageHandler((filters.TEXT | filters.CONTACT) & ~filters.COMMAND & ~filters.Regex(HOME_REGEX), ignore_support_text_messages),
            MessageHandler(filters.Regex(HOME_REGEX), back_to_menu),
            CommandHandler("start", start)
        ],
        per_chat=True,
        per_user=True
    )
    
    # Регистрация обработчиков.
    # ВАЖНО: Порядок регистрации имеет значение!
    # Сначала регистрируем специфичные обработчики, потом общие
    
    # 1. Обработчики администратора (для callback кнопок, если они используются)
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_delete, pattern="^admin_delete$"))
    application.add_handler(CallbackQueryHandler(admin_status, pattern="^admin_status$"))
    application.add_handler(CallbackQueryHandler(admin_back, pattern="^admin_back$"))
    
    # 3. Обработчики поддержки - КРИТИЧЕСКИ ВАЖНО: регистрируем САМЫМИ ПЕРВЫМИ!
    # Регистрируем в самом начале, чтобы они обрабатывались ДО ConversationHandler
    application.add_handler(CallbackQueryHandler(handle_support_question, pattern="^support_question_"))
    application.add_handler(CallbackQueryHandler(handle_support_contact_type, pattern="^support_contact_(phone|email)$"))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^support_back_to_menu$"))
    application.add_handler(CallbackQueryHandler(handle_support, pattern="^menu_support$"))
    
    # 3.1. Обработчик интеграции (регистрируем до handle_menu)
    application.add_handler(CallbackQueryHandler(handle_integration, pattern="^menu_integration$"))
    application.add_handler(CallbackQueryHandler(handle_integration_contact_type, pattern="^integration_contact_(phone|email)$"))
    
    # 2. Обработчики языков (должны быть до ConversationHandler)
    application.add_handler(CallbackQueryHandler(handle_lang, pattern="^lang_"))
    
    # 3. Обработчик "Позже" (должен быть до ConversationHandler)
    application.add_handler(CallbackQueryHandler(start_later, pattern="^start_later$"))
    
    # 4. Кнопка "Связаться с консультантом" - регистрируем САМОЙ ПЕРВОЙ из текстовых обработчиков
    # Используем кастомный фильтр для точного определения кнопки на всех языках
    # Фильтр проверяет точное совпадение текста с кнопкой на любом языке
    # Должна работать ВСЕГДА, даже во время активных диалогов
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & consultant_button_filter,
        handle_consultant_button
    ))
    
    # 5. Главное меню - регистрируем ПОСЛЕ обработчиков поддержки, но ДО ConversationHandler
    # Исключаем menu_support, menu_integration и menu_book_consultation через отрицательный lookahead
    application.add_handler(CallbackQueryHandler(handle_menu, pattern=r"^menu_(?!support$|integration$|book_consultation$)"))
    
    # 6. ConversationHandler для консультации (обрабатывает start_yes и menu_book_consultation)
    # Регистрируем ДО обработчиков свободного текста (support/integration),
    # иначе они будут перехватывать сообщения и ломать основной сценарий консультации.
    application.add_handler(consultation_handler)

    # 6.1 ЕДИНЫЙ текстовый роутер (support/integration/admin)
    # Так мы избегаем конфликтов обработчиков из‑за порядка регистрации.
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.CONTACT) & ~filters.COMMAND & ~filters.Regex(HOME_REGEX) & ~filters.Regex(r"^📊 Google Таблица$"),
        route_support_integration_input
    ))


    # 7. Команда /start (после ConversationHandler, чтобы сбрасывать активный диалог)
    application.add_handler(CommandHandler("start", start))
    
    # 7.1. Команды для администратора
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("refresh", refresh_command))
    application.add_handler(CommandHandler("test", test_keyboard_command))
    application.add_handler(CommandHandler("sheettest", sheettest_command))
    
    # 8. Обработчик кнопки Google Таблица для администратора (должен быть до общего текстового обработчика)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"^📊 Google Таблица$"),
        handle_google_sheet_button
    ))

    # 9. Обработчик текстового ввода администратора (для удаления/обновления строк)
    # Должен быть после ConversationHandler, чтобы не перехватывать сообщения из диалога
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.Regex(HOME_REGEX) & ~filters.Regex(r"^📊 Google Таблица$"),
        handle_admin_input
    ))
    
    # 11. Кнопка "🏠 Вернуться в главное меню" должна работать ВСЕГДА (reply keyboard)
    application.add_handler(MessageHandler(filters.Regex(HOME_REGEX), back_to_menu))

    # 12. Обработчик неизвестных callback (должен быть самым последним)
    application.add_handler(CallbackQueryHandler(handle_unknown_callback))

    async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка ошибок"""
        logger.exception("Unhandled error in handler", exc_info=context.error)
        # Если это callback query, отвечаем на него, чтобы кнопка не зависала
        if isinstance(update, Update) and update.callback_query:
            try:
                await update.callback_query.answer("Произошла ошибка. Попробуйте еще раз.")
            except:
                pass

    application.add_error_handler(on_error)
    
    # Запуск
    logger.info("🤖 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
