#!/usr/bin/env python3
"""
FrienGO - Telegram бот для организации встреч с друзьями

Основная точка входа в приложение.
"""

import asyncio
import logging
import os
import sys
import signal
from typing import Optional

from bot import FrienGoBot


def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('friendgo.log', encoding='utf-8')
        ]
    )
    
    # Подавляем избыточные логи от библиотек
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)


def get_bot_token() -> Optional[str]:
    """Получить токен бота из переменных окружения"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ Ошибка: Не найден токен бота!")
        print("💡 Установите переменную окружения TELEGRAM_BOT_TOKEN")
        print("   Например: export TELEGRAM_BOT_TOKEN='your_bot_token_here'")
        return None
    return token


async def main():
    """Главная функция"""
    print("🤖 Запуск FrienGO бота...")
    
    # Настройка логирования
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Получение токена
    token = get_bot_token()
    if not token:
        sys.exit(1)
    
    # Создание и запуск бота
    bot = FrienGoBot(token)
    
    # Обработка сигналов для корректного завершения
    def signal_handler(sig, frame):
        logger.info("Получен сигнал завершения, останавливаем бота...")
        asyncio.create_task(bot.stop_bot())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.start_bot()
        # Ожидаем завершения
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt, останавливаем бота...")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
    finally:
        await bot.stop_bot()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)
