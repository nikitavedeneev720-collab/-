import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Берем токен из переменных окружения
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    logger.error("BOT_TOKEN не найден в переменных окружения!")
    exit(1)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получена команда /start от {update.effective_user.username}")
    await update.message.reply_text(
        "🤖 Привет! Я твой бот и работаю!\n"
        "Отправь мне любое сообщение, и я отвечу!"
    )

# Обработчик текстовых сообщений
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получено сообщение: {update.message.text}")
    await update.message.reply_text(f"Ты написал: {update.message.text}")

def main():
    logger.info("Запуск бота...")
    
    # Создаем приложение
    app = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    # Запускаем в режиме вебхуков (для Bothost)
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Запуск вебхука на порту {port}")
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url="https://bot-1782822180-6410-klovechik.bothost.tech/" + TOKEN
    )

if __name__ == "__main__":
    main()
