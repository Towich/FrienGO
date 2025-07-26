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
        self.application.add_handler(CommandHandler("join", self.join_command))
        self.application.add_handler(CommandHandler("users", self.users_command))
        self.application.add_handler(CommandHandler("vote", self.create_voting_command))
        self.application.add_handler(CommandHandler("ping", self.ping_command))
        self.application.add_handler(CommandHandler("close", self.close_voting_command))
        
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
            "👤 Используй /join чтобы присоединиться для получения уведомлений\n"
            "🗳 Используй /vote чтобы создать голосование о днях встречи\n"
            "📢 Используй /ping чтобы напомнить друзьям проголосовать\n"
            "❓ Используй /help для получения подробной справки\n\n"
            "Готов помочь организовать вашу встречу! 🚀"
        )
        
        await update.message.reply_text(welcome_text)
    
    async def join_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /join - регистрация пользователя в системе"""
        user = update.effective_user
        if not user:
            await update.message.reply_text("❌ Не удалось получить информацию о пользователе")
            return
        
        # Сохраняем пользователя в БД
        db_user = User(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        self.db.save_user(db_user)
        
        # Проверяем, был ли пользователь уже зарегистрирован
        existing_user = self.db.get_user(user.id)
        if existing_user:
            user_display = existing_user.display_name
            username_part = f" (@{existing_user.username})" if existing_user.username else ""
            
            register_text = (
                f"✅ **Регистрация завершена!**\n\n"
                f"👤 **Имя:** {user_display}{username_part}\n"
                f"🆔 **ID:** {user.id}\n\n"
                f"Теперь вы находитесь в таблице известных пользователей!\n"
                f"📢 Вы будете получать уведомления о новых голосованиях и напоминания о необходимости проголосовать.\n\n"
                f"💡 Используйте /vote для создания голосования или /help для просмотра всех команд."
            )
        else:
            register_text = "❌ Произошла ошибка при регистрации. Попробуйте еще раз."
        
        await update.message.reply_text(register_text, parse_mode=ParseMode.MARKDOWN)
    
    async def users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /users - показать список зарегистрированных пользователей"""
        all_users = self.db.get_all_users()
        
        if not all_users:
            await update.message.reply_text(
                "📭 В системе пока нет зарегистрированных пользователей.\n"
                "Используйте /join для присоединения!"
            )
            return
        
        users_text = f"👥 **Зарегистрированные пользователи ({len(all_users)}):**\n\n"
        
        for i, user in enumerate(all_users, 1):
            user_display = user.display_name
            username_part = f" (@{user.username})" if user.username else ""
            users_text += f"{i}. {user_display}{username_part} (ID: {user.user_id})\n"
        
        users_text += f"\n💡 Все эти пользователи будут получать уведомления о голосованиях."
        
        # Разбиваем сообщение на части, если оно слишком длинное
        if len(users_text) > 4000:
            # Отправляем заголовок отдельно
            header = f"👥 **Зарегистрированные пользователи ({len(all_users)}):**\n\n"
            await update.message.reply_text(header, parse_mode=ParseMode.MARKDOWN)
            
            # Отправляем пользователей группами по 20
            chunk_size = 20
            for i in range(0, len(all_users), chunk_size):
                chunk_users = all_users[i:i + chunk_size]
                chunk_text = ""
                for j, user in enumerate(chunk_users, i + 1):
                    user_display = user.display_name
                    username_part = f" (@{user.username})" if user.username else ""
                    chunk_text += f"{j}. {user_display}{username_part} (ID: {user.user_id})\n"
                
                await update.message.reply_text(chunk_text, parse_mode=ParseMode.MARKDOWN)
            
            # Отправляем заключение
            footer = f"\n💡 Все эти пользователи будут получать уведомления о голосованиях."
            await update.message.reply_text(footer, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(users_text, parse_mode=ParseMode.MARKDOWN)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = (
            "📖 **Справка по командам FrienGO бота**\n\n"
            "**Основные команды:**\n"
            "👤 `/join` - Присоединиться к системе для получения уведомлений\n"
            "👥 `/users` - Показать список зарегистрированных пользователей\n"
            "🗳 `/vote` - Создать новое голосование о днях встречи\n"
            "📢 `/ping` - Напомнить непроголосовавшим участникам\n"
            "🏁 `/close` - Завершить голосование и показать детальные результаты\n\n"
            "**Как пользоваться:**\n"
            "0️⃣ Присоединитесь командой `/join` для получения уведомлений\n"
            "1️⃣ Создайте голосование командой `/vote`\n"
            "2️⃣ Выберите подходящие дни, нажимая на кнопки\n"
            "3️⃣ Можете отменить свой голос, нажав на кнопку повторно\n"
            "4️⃣ Используйте `/ping` чтобы напомнить друзьям\n"
            "5️⃣ Завершите голосование командой `/close`\n\n"
            "**Автоматические напоминания:**\n"
            "⏰ Бот автоматически напомнит через 24, 48 и 72 часа\n\n"
            "**Особенности:**\n"
            "✅ Множественный выбор дней\n"
            "🔄 Возможность отмены голоса\n"
            "📊 Автоматический подсчет голосов\n"
            "👥 Отслеживание количества проголосовавших\n"
            "📌 Автоматическое закрепление сообщений с голосованием\n"
            "📢 Уведомления для зарегистрированных пользователей\n\n"
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
            # Раскрепляем предыдущие сообщения голосований (если есть)
            last_message_id = self.db.get_last_closed_voting_message_id(chat_id)
            if last_message_id:
                try:
                    await self.application.bot.unpin_chat_message(
                        chat_id=chat_id,
                        message_id=last_message_id
                    )
                    self.logger.info(f"Unpinned previous voting message {last_message_id} in chat {chat_id}")
                except Exception as e:
                    self.logger.warning(f"Failed to unpin previous message: {e}")
            
            # Создаем голосование
            voting = self.voting_service.create_voting(chat_id)
            
            # Формируем сообщение и клавиатуру
            message_text = self._format_voting_message(voting.voting_id)
            keyboard = self._create_voting_keyboard(voting.voting_id)
            
            # Отправляем сообщение
            sent_message = await update.message.reply_text(
                message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Обновляем ID сообщения в БД
            self.db.update_voting_message_id(voting.voting_id, sent_message.message_id)
            
            # Закрепляем сообщение с голосованием
            try:
                await self.application.bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=sent_message.message_id,
                    disable_notification=True  # Не отправляем уведомление о закреплении
                )
                self.logger.info(f"Pinned voting message {sent_message.message_id} in chat {chat_id}")
            except Exception as e:
                self.logger.warning(f"Failed to pin message: {e}. Bot may not have admin rights.")
                # Не блокируем создание голосования если не удалось закрепить
            
        except ValueError as e:
            await update.message.reply_text(f"❌ {str(e)}")
        except Exception as e:
            self.logger.error(f"Error creating voting: {e}")
            await update.message.reply_text("❌ Произошла ошибка при создании голосования")
    
    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /ping - напомнить непроголосовавшим"""
        chat_id = update.effective_chat.id
        
        voting = self.voting_service.get_active_voting(chat_id)
        if not voting:
            await update.message.reply_text("📝 В данном чате нет активного голосования.")
            return
        
        # Получаем всех известных пользователей (включая новых друзей)
        all_users = self.db.get_all_users()
        non_voted_users = self.voting_service.get_non_voted_users(voting.voting_id, all_users)
        
        # Отправляем пинг молча (без подтверждающего сообщения)
        await self.scheduler.send_manual_ping(chat_id, voting.voting_id, non_voted_users)
    
    async def close_voting_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /close - завершение голосования"""
        chat_id = update.effective_chat.id
        
        voting = self.voting_service.get_active_voting(chat_id)
        if not voting:
            await update.message.reply_text("📝 В данном чате нет активного голосования.")
            return
        
        # Раскрепляем сообщение с голосованием перед закрытием
        if voting.message_id:
            try:
                await self.application.bot.unpin_chat_message(
                    chat_id=chat_id,
                    message_id=voting.message_id
                )
                self.logger.info(f"Unpinned voting message {voting.message_id} in chat {chat_id}")
            except Exception as e:
                self.logger.warning(f"Failed to unpin message: {e}. Message may already be unpinned.")
        
        # Завершаем голосование
        results = self.voting_service.close_voting(voting.voting_id)
        if not results:
            await update.message.reply_text("❌ Ошибка при завершении голосования.")
            return
        
        # Формируем сообщение с топ-3 результатами
        message = f"🏁 **Голосование завершено!**\n\n"
        message += f"🗳 {results['title']}\n"
        message += f"📊 Итого проголосовало: {results['voted_users']}/{results['total_users']}\n\n"
        message += "🏆 **Топ-3 дня:**\n"
        
        for i, option in enumerate(results['top_3'], 1):
            emoji = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            message += f"{emoji} {option['description']} — {option['votes_count']} голосов\n"
        
        if len(results['top_3']) == 0:
            message += "❌ Никто не проголосовал\n"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        
        # Показываем детальные результаты
        await self._send_detailed_results(update, voting.voting_id)
    
    async def _send_detailed_results(self, update: Update, voting_id: int):
        """Отправить детальные результаты голосования"""
        # Получаем детальные результаты
        results = self.voting_service.get_detailed_results(voting_id)
        if not results:
            await update.message.reply_text("❌ Ошибка при получении детальных результатов.")
            return
        
        # Формируем подробное сообщение
        message = f"📋 **Детальные результаты:**\n\n"
        
        for option in results['options']:
            message += f"📅 **{option['description']}**: {option['votes_count']} голосов\n"
            if option['voters']:
                for voter in option['voters']:
                    message += f"   👤 {voter['display_name']} {voter['username']}\n"
            else:
                message += f"   ❌ Никто не голосовал\n"
            message += "\n"
        
        # Отправляем сообщение частями, если оно слишком длинное
        if len(message) > 4000:
            # Разбиваем на части по опциям
            base_message = f"📋 **Детальные результаты:**\n\n"
            await update.message.reply_text(base_message, parse_mode=ParseMode.MARKDOWN)
            
            for option in results['options']:
                option_message = f"📅 **{option['description']}**: {option['votes_count']} голосов\n"
                if option['voters']:
                    for voter in option['voters']:
                        option_message += f"   👤 {voter['display_name']} {voter['username']}\n"
                else:
                    option_message += f"   ❌ Никто не голосовал\n"
                
                await update.message.reply_text(option_message, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
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
                    await self._update_voting_message(query, voting_id)
                    await query.answer("Голос отменен")
                else:
                    await query.answer(message, show_alert=True)
            else:
                # Если не голосовал - добавляем голос
                success, message = self.voting_service.vote_for_option(user.id, option_id, voting_id)
                
                if success:
                    # Обновляем сообщение
                    await self._update_voting_message(query, voting_id)
                    # Отправляем уведомление о голосе
                    await self._send_vote_notification(update.effective_chat.id, user, voting_id, option_id)
                else:
                    await query.answer(message, show_alert=True)
    
    async def _update_voting_message(self, query, voting_id: int):
        """Обновить сообщение с голосованием"""
        message_text = self._format_voting_message(voting_id)
        keyboard = self._create_voting_keyboard(voting_id)
        
        try:
            await query.edit_message_text(
                message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            self.logger.error(f"Error updating voting message: {e}")
    
    async def _send_vote_notification(self, chat_id: int, user, voting_id: int, option_id: int):
        """Отправить уведомление о том, что пользователь проголосовал"""
        stats = self.voting_service.get_voting_stats(voting_id)
        if not stats:
            return
        
        # Находим информацию о выбранной опции
        selected_option = None
        for option in stats['options']:
            if option['option_id'] == option_id:
                selected_option = option
                break
        
        if not selected_option:
            return
        
        user_name = user.first_name or user.username or f"User_{user.id}"
        
        message = (f"✅ {user_name} проголосовал за {selected_option['description']}!\n"
                  f"📊 Проголосовало: {stats['voted_users']}/{stats['total_users']}")
        
        try:
            await self.application.bot.send_message(chat_id, message)
        except Exception as e:
            self.logger.error(f"Error sending vote notification: {e}")
    
    def _format_voting_message(self, voting_id: int) -> str:
        """Форматировать сообщение с голосованием"""
        results = self.voting_service.get_detailed_results(voting_id)
        if not results:
            return "Голосование не найдено"
        
        message = f"🗳 **{results['title']}**\n\n"
        message += f"📊 Проголосовало: {results['voted_users']}/{results['total_users']}\n\n"
        
        # Сортируем опции по количеству голосов и берем топ-3
        sorted_options = sorted(results['options'], key=lambda x: x['votes_count'], reverse=True)
        top_3 = sorted_options[:3]
        
        # Показываем топ-3 дня с голосующими
        if any(option['votes_count'] > 0 for option in top_3):
            message += "🏆 **Топ дни:**\n"
            
            for i, option in enumerate(top_3):
                if option['votes_count'] > 0:
                    # Медали для топ-3
                    medals = ["🥇", "🥈", "🥉"]
                    medal = medals[i] if i < len(medals) else f"{i+1}."
                    
                    message += f"{medal} **{option['description']}** ({option['votes_count']} голосов)\n"
                    
                    # Показываем кто проголосовал (только display_name, без username)
                    if option['voters']:
                        voter_names = [voter['display_name'] for voter in option['voters']]
                        message += f"   👥 {', '.join(voter_names)}\n"
                    
                    message += "\n"
        
        return message
    
    def _create_voting_keyboard(self, voting_id: int) -> InlineKeyboardMarkup:
        """Создать клавиатуру для голосования"""
        voting = self.db.get_voting(voting_id)
        if not voting:
            return InlineKeyboardMarkup([])
        
        # Получаем статистику для подсчета голосов
        stats = self.voting_service.get_voting_stats(voting_id)
        if not stats:
            return InlineKeyboardMarkup([])
        
        # Создаем словарь для быстрого поиска количества голосов по option_id
        votes_count = {option['option_id']: option['votes_count'] for option in stats['options']}
        
        keyboard = []
        for option in voting.options:
            # Получаем количество голосов для этой опции
            count = votes_count.get(option.option_id, 0)
            
            # Формируем текст кнопки с количеством голосов
            if count > 0:
                button_text = f"{option.description} ({count})"
            else:
                button_text = option.description
            
            callback_data = f"vote:{voting_id}:{option.option_id}"
            button = InlineKeyboardButton(button_text, callback_data=callback_data)
            keyboard.append([button])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def _send_ping_message(self, chat_id: int, voting_id: int, message: str):
        """Callback функция для отправки ping сообщений"""
        try:
            await self.application.bot.send_message(
                chat_id, 
                message, 
                parse_mode=ParseMode.MARKDOWN
            )
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