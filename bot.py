import asyncio
import logging
import os
from typing import List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

from models import User, VoteStatus
from database import DatabaseManager
from voting import VotingService
from scheduler import PingScheduler


class FrienGoBot:
    """Основной класс телеграм бота для голосований о встречах"""
    
    def __init__(self, token: str, db_path: str = "friendgo.db"):
        self.token = token
        self.db = DatabaseManager(db_path)
        self.voting_service = VotingService(self.db)
        self.scheduler = PingScheduler(self.db, self.voting_service)
        self.application = Application.builder().token(token).build()
        self.logger = logging.getLogger(__name__)
        
        # Настройка планировщика
        self.scheduler.set_ping_callback(self._send_ping_message)
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Настройка обработчиков команд и callback'ов"""
        # Команды
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("vote", self.create_voting_command))
        self.application.add_handler(CommandHandler("ping", self.ping_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # Callback обработчик для кнопок
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Обработчик ошибок
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        if user:
            # Сохраняем пользователя в БД
            db_user = User(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            self.db.save_user(db_user)
        
        welcome_text = (
            "👋 Привет! Я бот FrienGO для организации встреч с друзьями!\n\n"
            "🗳 Используй /vote чтобы создать голосование о днях встречи\n"
            "📊 Используй /status чтобы посмотреть текущее голосование\n"
            "📢 Используй /ping чтобы напомнить друзьям проголосовать\n"
            "❓ Используй /help для получения подробной справки\n\n"
            "Готов помочь организовать вашу встречу! 🚀"
        )
        
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = (
            "📖 **Справка по командам FrienGO бота**\n\n"
            "**Основные команды:**\n"
            "🗳 `/vote` - Создать новое голосование о днях встречи\n"
            "📊 `/status` - Показать текущее активное голосование\n"
            "📢 `/ping` - Напомнить непроголосовавшим участникам\n\n"
            "**Как пользоваться:**\n"
            "1️⃣ Создайте голосование командой `/vote`\n"
            "2️⃣ Выберите подходящие дни, нажимая на кнопки\n"
            "3️⃣ Можете отменить свой голос, нажав на кнопку повторно\n"
            "4️⃣ Используйте `/ping` чтобы напомнить друзьям\n\n"
            "**Автоматические напоминания:**\n"
            "⏰ Бот автоматически напомнит через 24, 48 и 72 часа\n\n"
            "**Особенности:**\n"
            "✅ Множественный выбор дней\n"
            "🔄 Возможность отмены голоса\n"
            "📊 Автоматический подсчет голосов\n"
            "👥 Отслеживание количества проголосовавших\n\n"
            "Приятного использования! 🎉"
        )
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def create_voting_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /vote - создание нового голосования"""
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        # Сохраняем пользователя
        if user:
            db_user = User(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            self.db.save_user(db_user)
        
        try:
            # Создаем голосование
            voting = self.voting_service.create_voting(chat_id)
            
            # Формируем сообщение и клавиатуру
            message_text = self._format_voting_message(voting.voting_id)
            keyboard = self._create_voting_keyboard(voting.voting_id, user.id)
            
            # Отправляем сообщение
            sent_message = await update.message.reply_text(
                message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Обновляем ID сообщения в БД
            self.db.update_voting_message_id(voting.voting_id, sent_message.message_id)
            
        except ValueError as e:
            await update.message.reply_text(f"❌ {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating voting: {e}")
            await update.message.reply_text("❌ Произошла ошибка при создании голосования")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status - показать статус голосования"""
        chat_id = update.effective_chat.id
        
        voting = self.voting_service.get_active_voting(chat_id)
        if not voting:
            await update.message.reply_text("📝 В данном чате нет активного голосования.\nИспользуйте /vote для создания нового!")
            return
        
        message_text = self._format_voting_message(voting.voting_id)
        keyboard = self._create_voting_keyboard(voting.voting_id, update.effective_user.id if update.effective_user else None)
        
        await update.message.reply_text(
            message_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /ping - напомнить непроголосовавшим"""
        chat_id = update.effective_chat.id
        
        voting = self.voting_service.get_active_voting(chat_id)
        if not voting:
            await update.message.reply_text("📝 В данном чате нет активного голосования.")
            return
        
        # Получаем всех известных пользователей чата
        chat_users = self.db.get_chat_users(chat_id)
        non_voted_users = self.voting_service.get_non_voted_users(voting.voting_id, chat_users)
        
        result = await self.scheduler.send_manual_ping(chat_id, voting.voting_id, non_voted_users)
        await update.message.reply_text(result)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на inline кнопки"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        if not user:
            return
        
        # Сохраняем пользователя
        db_user = User(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        self.db.save_user(db_user)
        
        # Парсим callback data
        try:
            action, voting_id, option_id = query.data.split(":")
            voting_id = int(voting_id)
            option_id = int(option_id)
        except ValueError:
            await query.edit_message_text("❌ Некорректные данные")
            return
        
        if action == "vote":
            # Получаем текущее голосование для проверки
            voting = self.db.get_voting(voting_id)
            if not voting:
                await query.answer("Голосование не найдено", show_alert=True)
                return
            
            # Проверяем, голосовал ли уже пользователь за эту опцию
            if voting.has_user_voted_for_option(user.id, option_id):
                # Если уже голосовал - отменяем голос
                success, message = self.voting_service.remove_vote(user.id, option_id, voting_id)
                if success:
                    await self._update_voting_message(query, voting_id, user.id)
                    await query.answer("Голос отменен")
                else:
                    await query.answer(message, show_alert=True)
            else:
                # Если не голосовал - добавляем голос
                success, message = self.voting_service.vote_for_option(user.id, option_id, voting_id)
                
                if success:
                    # Обновляем сообщение
                    await self._update_voting_message(query, voting_id, user.id)
                    # Отправляем уведомление о голосе
                    await self._send_vote_notification(update.effective_chat.id, user, voting_id)
                else:
                    await query.answer(message, show_alert=True)
    
    async def _update_voting_message(self, query, voting_id: int, user_id: int = None):
        """Обновить сообщение с голосованием"""
        message_text = self._format_voting_message(voting_id)
        keyboard = self._create_voting_keyboard(voting_id, user_id)
        
        try:
            await query.edit_message_text(
                message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            self.logger.error(f"Error updating voting message: {e}")
    
    async def _send_vote_notification(self, chat_id: int, user, voting_id: int):
        """Отправить уведомление о том, что пользователь проголосовал"""
        stats = self.voting_service.get_voting_stats(voting_id)
        if not stats:
            return
        
        user_name = user.first_name or user.username or f"User_{user.id}"
        message = (f"✅ {user_name} проголосовал!\n"
                  f"📊 Проголосовало: {stats['voted_users']}/{stats['total_users']}")
        
        try:
            await self.application.bot.send_message(chat_id, message)
        except Exception as e:
            self.logger.error(f"Error sending vote notification: {e}")
    
    def _format_voting_message(self, voting_id: int) -> str:
        """Форматировать сообщение с голосованием"""
        stats = self.voting_service.get_voting_stats(voting_id)
        if not stats:
            return "Голосование не найдено"
        
        message = f"🗳 **{stats['title']}**\n\n"
        
        for option in stats['options']:
            votes_emoji = "✅" * option['votes_count'] if option['votes_count'] > 0 else ""
            message += f"{option['description']}: {option['votes_count']} голосов {votes_emoji}\n"
        
        message += f"\n📊 Проголосовало: {stats['voted_users']}/{stats['total_users']}"
        
        return message
    
    def _create_voting_keyboard(self, voting_id: int, user_id: int = None) -> InlineKeyboardMarkup:
        """Создать клавиатуру для голосования"""
        voting = self.db.get_voting(voting_id)
        if not voting:
            return InlineKeyboardMarkup([])
        
        keyboard = []
        for option in voting.options:
            # Проверяем, голосовал ли текущий пользователь за эту опцию
            user_voted = False
            if user_id and voting.has_user_voted_for_option(user_id, option.option_id):
                user_voted = True
            
            # Кнопка для голосования/отмены голоса
            vote_emoji = "✅" if user_voted else "⬜"
            button_text = f"{vote_emoji} {option.description}"
            callback_data = f"vote:{voting_id}:{option.option_id}"
            
            button = InlineKeyboardButton(button_text, callback_data=callback_data)
            keyboard.append([button])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def _send_ping_message(self, chat_id: int, voting_id: int, message: str):
        """Callback функция для отправки ping сообщений"""
        try:
            await self.application.bot.send_message(chat_id, message)
        except Exception as e:
            self.logger.error(f"Error sending ping message: {e}")
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        self.logger.error(f"Update {update} caused error {context.error}")
    
    async def start_bot(self):
        """Запустить бота"""
        self.logger.info("Starting FrienGO bot...")
        
        # Запускаем планировщик в фоне
        asyncio.create_task(self.scheduler.start())
        
        # Запускаем бота
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        self.logger.info("FrienGO bot started successfully!")
    
    async def stop_bot(self):
        """Остановить бота"""
        self.logger.info("Stopping FrienGO bot...")
        
        self.scheduler.stop()
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        
        self.logger.info("FrienGO bot stopped") 