import asyncio
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
    CallbackQueryHandler,
)
from gigachat import GigaChat

# --- Импортируем наши модули ---
# Загружаем токены, базу данных и состояния из config.py
from config import TELEGRAM_BOT_TOKEN, GIGACHAT_CREDENTIALS, VENUES_DB, SELECT_LANG, BUDGET, PEOPLE, DURATION, INTERESTS
# Загружаем все тексты и промты из prompts.py
from prompts import STRINGS, CLASSIFIER_PROMPT, FINAL_ANSWER_PROMPT

# Настройка логирования для отладки
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Новая функция для поиска по нашей JSON базе ---
def find_venues_in_db(category: str) -> list:
    """
    Ищет заведения в загруженной базе VENUES_DB по заданной категории.
    Если категория не найдена, возвращает заведения из категории 'GENERAL'.
    """
    logger.info(f"🔧 Поиск в локальной базе по категории: '{category}'...")
    # .get() безопасно вернет None, если ключа нет, а or обеспечит фолбэк
    venues = VENUES_DB.get(category.upper()) or VENUES_DB.get('GENERAL', [])
    random.shuffle(venues)
    return venues[:5] # Возвращаем до 5 случайных мест

# --- Функции-шаги для диалога (ConversationHandler) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог, предлагает выбрать язык."""
    context.user_data.clear() # Очищаем данные от предыдущих сессий
    keyboard = [[InlineKeyboardButton("Русский 🇷🇺", callback_data='ru')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        STRINGS['ru']['welcome'],
        reply_markup=reply_markup
    )
    return SELECT_LANG

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор языка и задает следующий вопрос."""
    query = update.callback_query
    await query.answer()
    lang = query.data
    context.user_data['lang'] = lang

    await query.edit_message_text(text=STRINGS[lang]['lang_selected'])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=STRINGS[lang]['ask_budget']
    )
    return BUDGET

async def budget_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет бюджет и задает вопрос о количестве людей."""
    lang = context.user_data['lang']
    context.user_data['budget'] = update.message.text
    await update.message.reply_text(STRINGS[lang]['ask_people'])
    return PEOPLE

async def people_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет количество людей и задает вопрос о времени."""
    lang = context.user_data['lang']
    context.user_data['people'] = update.message.text
    await update.message.reply_text(STRINGS[lang]['ask_duration'])
    return DURATION

async def duration_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет время и задает финальный вопрос об интересах."""
    lang = context.user_data['lang']
    context.user_data['duration'] = update.message.text
    await update.message.reply_text(STRINGS[lang]['ask_interests'])
    return INTERESTS

async def interests_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Главный шаг: классифицирует интересы, ищет места в базе и выдает результат.
    """
    lang = context.user_data['lang']
    user_interests = update.message.text
    context.user_data['interests'] = user_interests

    await update.message.reply_text(STRINGS[lang]['processing'])

    try:
        async with GigaChat(credentials=GIGACHAT_CREDENTIALS, verify_ssl_certs=False) as giga:
            # 1. Классифицируем запрос пользователя в категорию
            logger.info("🤖 GigaChat: Классификация интересов...")
            response_category = await giga.achat(
                payload={
                    "model": "GigaChat:latest",
                    "messages": [
                        {"role": "system", "content": CLASSIFIER_PROMPT},
                        {"role": "user", "content": user_interests},
                    ],
                    "temperature": 0.1,
                }
            )
            category = response_category.choices[0].message.content.strip()
            logger.info(f"✅ GigaChat: Категория определена как '{category}'")

            # 2. Ищем места в нашей локальной базе по полученной категории
            venues = find_venues_in_db(category)

            if not venues:
                await update.message.reply_text("К сожалению, я не нашел подходящих мест. Попробуйте описать свои интересы по-другому.")
                return ConversationHandler.END

            # 3. Форматируем красивый ответ с помощью GigaChat
            logger.info("🤖 GigaChat: Форматирование финального ответа...")
            final_prompt_input = f"Список мест в формате JSON:\n{str(venues)}\n\nСделай из этого списка красивый ответ для пользователя."
            response_final = await giga.achat(
                 payload={
                    "model": "GigaChat:latest",
                    "messages": [
                        {"role": "system", "content": FINAL_ANSWER_PROMPT},
                        {"role": "user", "content": final_prompt_input},
                    ],
                    "temperature": 0.7,
                }
            )
            formatted_venues = response_final.choices[0].message.content

            # Отправляем итоговый ответ
            await update.message.reply_text(
                f"{STRINGS[lang]['result_intro']}\n\n{formatted_venues}{STRINGS[lang]['final_prompt']}",
                parse_mode=ParseMode.MARKDOWN
            )

    except Exception as e:
        logger.error(f"❌ Произошла ошибка: {e}")
        await update.message.reply_text(STRINGS[lang]['error'])

    return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог."""
    lang = context.user_data.get('lang', 'ru')
    await update.message.reply_text(STRINGS[lang]['cancel'])
    return ConversationHandler.END


# --- Основной блок запуска бота ---
def main():
    """Главная функция, которая собирает и запускает бота."""
    if not TELEGRAM_BOT_TOKEN or not GIGACHAT_CREDENTIALS:
        print("❌ ОШИБКА: Один или несколько обязательных токенов (TELEGRAM_BOT_TOKEN, GIGACHAT_CREDENTIALS) не найдены в .env файле!")
        return

    # Создаем приложение
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Создаем обработчик диалога
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start_command)],
        states={
            SELECT_LANG: [CallbackQueryHandler(button_handler)],
            BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, budget_step)],
            PEOPLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, people_step)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, duration_step)],
            INTERESTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, interests_step)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )

    app.add_handler(conv_handler)

    print("✅ Бот запущен (v1.0 REFACTORED)")
    print("🚀 Ожидание команд...")
    
    # Запускаем бота
    app.run_polling()

if __name__ == "__main__":
    main()

