import asyncio
import logging
from datetime import datetime
from typing import Callable, List, Optional

from models import PingSchedule, User
from database import DatabaseManager
from voting import VotingService


class PingScheduler:
    """Планировщик для автоматических пингов"""
    
    def __init__(self, db_manager: DatabaseManager, voting_service: VotingService):
        self.db = db_manager
        self.voting_service = voting_service
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.ping_callback: Optional[Callable] = None
    
    def set_ping_callback(self, callback: Callable):
        """Установить callback функцию для отправки пингов"""
        self.ping_callback = callback
    
    async def start(self):
        """Запустить планировщик"""
        self.is_running = True
        self.logger.info("Ping scheduler started")
        
        while self.is_running:
            try:
                await self._check_and_send_pings()
                # Проверяем каждые 5 минут
                await asyncio.sleep(300)
            except Exception as e:
                self.logger.error(f"Error in ping scheduler: {e}")
                await asyncio.sleep(60)  # При ошибке ждем минуту
    
    def stop(self):
        """Остановить планировщик"""
        self.is_running = False
        self.logger.info("Ping scheduler stopped")
    
    async def _check_and_send_pings(self):
        """Проверить и отправить ожидающие пинги"""
        if not self.ping_callback:
            return
        
        current_time = datetime.now()
        pending_schedules = self.db.get_pending_pings(current_time)
        
        for schedule in pending_schedules:
            voting = self.db.get_voting(schedule.voting_id)
            if not voting:
                continue
            
            # Определить тип пинга
            ping_types = []
            if schedule.ping_24h_at <= current_time and not schedule.is_24h_sent:
                ping_types.append("24h")
            if schedule.ping_48h_at <= current_time and not schedule.is_48h_sent:
                ping_types.append("48h")
            if schedule.ping_72h_at <= current_time and not schedule.is_72h_sent:
                ping_types.append("72h")
            
            for ping_type in ping_types:
                try:
                    await self._send_ping(voting.chat_id, voting.voting_id, ping_type)
                    self.db.mark_ping_sent(schedule.schedule_id, ping_type)
                    self.logger.info(f"Sent {ping_type} ping for voting {voting.voting_id}")
                except Exception as e:
                    self.logger.error(f"Failed to send {ping_type} ping: {e}")
    
    async def _send_ping(self, chat_id: int, voting_id: int, ping_type: str):
        """Отправить пинг в чат"""
        if not self.ping_callback:
            return
        
        # Получаем список всех известных пользователей чата
        chat_users = self.db.get_chat_users(chat_id)
        
        # Получаем список не проголосовавших пользователей
        non_voted_users = self.voting_service.get_non_voted_users(voting_id, chat_users)
        
        # Создаем сообщение с пингом
        message = self._get_ping_message(ping_type, non_voted_users)
        await self.ping_callback(chat_id, voting_id, message)
    
    def _get_ping_message(self, ping_type: str, non_voted_users: List[User]) -> str:
        """Получить текст сообщения для пинга"""
        time_messages = {
            "24h": "⏰ Прошло 24 часа с момента создания голосования!",
            "48h": "⏰ Прошло 48 часов с момента создания голосования!",
            "72h": "🚨 Прошло 72 часа с момента создания голосования!"
        }
        
        base_message = time_messages.get(ping_type, "⏰ Напоминание о голосовании!")
        
        if not non_voted_users:
            return f"{base_message}\n\n🎉 Все пользователи уже проголосовали!"
        
        # Создаем список упоминаний пользователей по их Telegram ID
        mentions = []
        for user in non_voted_users:
            if user.username:
                # Если есть username, используем @username
                mentions.append(f"@{user.username}")
            else:
                # Если нет username, используем упоминание по ID
                display_name = user.display_name
                mentions.append(f"[{display_name}](tg://user?id={user.user_id})")
        
        return (f"{base_message}\n\n"
               f"📣 Не забудьте проголосовать за удобные дни для встречи!\n\n"
               f"👥 Ждем голосов от: {', '.join(mentions)}\n\n"
               f"🗳 Нажмите на кнопки под сообщением с голосованием!")
    
    async def send_manual_ping(self, chat_id: int, voting_id: int, 
                             non_voted_users: List[User]) -> str:
        """Отправить ручной пинг непроголосовавшим пользователям"""
        if not self.ping_callback:
            return "Ping callback не установлен"
        
        if not non_voted_users:
            return "Все пользователи уже проголосовали! 🎉"
        
        # Создаем список упоминаний пользователей по их Telegram ID
        mentions = []
        for user in non_voted_users:
            if user.username:
                # Если есть username, используем @username
                mentions.append(f"@{user.username}")
            else:
                # Если нет username, используем упоминание по ID
                display_name = user.display_name
                mentions.append(f"[{display_name}](tg://user?id={user.user_id})")
        
        message = (f"📢 Ребята, не забудьте проголосовать!\n\n"
                  f"👥 Ждем голосов от: {', '.join(mentions)}\n\n"
                  f"🗳 Нажмите на кнопки под сообщением с голосованием!")
        
        try:
            await self.ping_callback(chat_id, voting_id, message)
            return f"Пинг отправлен! Ожидают голосования: {len(non_voted_users)} человек"
        except Exception as e:
            self.logger.error(f"Failed to send manual ping: {e}")
            return f"Ошибка при отправке пинга: {e}" 