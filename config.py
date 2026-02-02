import os
import json
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# --- Секретные ключи ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GIGACHAT_CREDENTIALS = os.getenv('GIGACHAT_CREDENTIALS')

# --- База данных ---
# Загружаем нашу новую JSON базу данных в память при старте
try:
    with open('database.json', 'r', encoding='utf-8') as f:
        VENUES_DB = json.load(f)
except FileNotFoundError:
    print("❌ ОШИБКА: Файл database.json не найден! Убедитесь, что он находится в той же директории.")
    VENUES_DB = {}
except json.JSONDecodeError:
    print("❌ ОШИБКА: Не удалось прочитать database.json! Проверьте синтаксис файла.")
    VENUES_DB = {}


# --- Состояния для ConversationHandler ---
# Определяем шаги диалога в виде констант
SELECT_LANG, BUDGET, PEOPLE, DURATION, INTERESTS = range(5)
