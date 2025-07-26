from datetime import datetime, date, timedelta
from typing import List, Optional, Set, Tuple
import logging

from models import Voting, VoteOption, Vote, User, VoteStatus, PingSchedule
from database import DatabaseManager


class VotingService:
    """Сервис для управления голосованиями"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.logger = logging.getLogger(__name__)
    
    def generate_weekend_dates(self, start_date: date = None, weeks: int = 4) -> List[date]:
        """Генерирует даты выходных дней на указанное количество недель вперед"""
        if start_date is None:
            start_date = date.today()
        
        weekends = []
        current_date = start_date
        
        # Найти ближайшую субботу
        days_until_saturday = (5 - current_date.weekday()) % 7
        if days_until_saturday == 0 and current_date.weekday() == 5:
            # Если сегодня суббота, начинаем с сегодня
            saturday = current_date
        else:
            saturday = current_date + timedelta(days=days_until_saturday)
        
        # Генерируем выходные на указанное количество недель
        for week in range(weeks):
            current_saturday = saturday + timedelta(weeks=week)
            current_sunday = current_saturday + timedelta(days=1)
            weekends.extend([current_saturday, current_sunday])
        
        return weekends
    
    def create_voting(self, chat_id: int, title: str = None, message_thread_id: int = None) -> Voting:
        """Создать новое голосование"""
        # Проверить, есть ли активное голосование в чате
        active_voting = self.db.get_active_voting_by_chat(chat_id)
        if active_voting:
            raise ValueError("В чате уже есть активное голосование")
        
        if title is None:
            title = f"Когда собираемся? 📅"
        
        # Генерируем выходные дни
        weekend_dates = self.generate_weekend_dates()
        
        # Создаем объект голосования
        voting = Voting(
            voting_id=0,  # Будет установлен в БД
            chat_id=chat_id,
            message_id=None,
            message_thread_id=message_thread_id,
            title=title,
            created_at=datetime.now(),
            status=VoteStatus.ACTIVE
        )
        
        # Создаем опции для выходных дней
        for i, weekend_date in enumerate(weekend_dates):
            option = VoteOption.create_from_date(0, 0, weekend_date)
            voting.options.append(option)
        
        # Добавляем опцию "Не пойду:("
        not_going_option = VoteOption.create_custom(0, 0, "Не пойду:(")
        voting.options.append(not_going_option)
        
        # Сохраняем в БД
        voting = self.db.create_voting(voting)
        
        # Создаем расписание пингов
        self._create_ping_schedule(voting.voting_id)
        
        self.logger.info(f"Created voting {voting.voting_id} in chat {chat_id}")
        return voting
    
    def _create_ping_schedule(self, voting_id: int):
        """Создать расписание пингов для голосования"""
        now = datetime.now()
        schedule = PingSchedule(
            schedule_id=0,
            voting_id=voting_id,
            ping_24h_at=now + timedelta(hours=24),
            ping_48h_at=now + timedelta(hours=48), 
            ping_72h_at=now + timedelta(hours=72)
        )
        self.db.create_ping_schedule(schedule)
    
    def vote_for_option(self, user_id: int, option_id: int, voting_id: int) -> Tuple[bool, str]:
        """Проголосовать за опцию"""
        voting = self.db.get_voting(voting_id)
        if not voting:
            return False, "Голосование не найдено"
        
        if voting.status != VoteStatus.ACTIVE:
            return False, "Голосование уже завершено"
        
        # Проверить, голосовал ли уже пользователь за эту опцию
        if voting.has_user_voted_for_option(user_id, option_id):
            return False, "Вы уже голосовали за этот день"
        
        # Добавить голос
        vote = Vote(
            vote_id=0,
            user_id=user_id,
            option_id=option_id,
            voting_id=voting_id,
            created_at=datetime.now()
        )
        
        self.db.add_vote(vote)
        self.logger.info(f"User {user_id} voted for option {option_id} in voting {voting_id}")
        return True, "Голос засчитан!"
    
    def remove_vote(self, user_id: int, option_id: int, voting_id: int) -> Tuple[bool, str]:
        """Удалить голос пользователя за опцию"""
        voting = self.db.get_voting(voting_id)
        if not voting:
            return False, "Голосование не найдено"
        
        if voting.status != VoteStatus.ACTIVE:
            return False, "Голосование уже завершено"
        
        # Проверить, голосовал ли пользователь за эту опцию
        if not voting.has_user_voted_for_option(user_id, option_id):
            return False, "Вы не голосовали за этот день"
        
        # Удалить голос
        success = self.db.remove_vote(user_id, option_id, voting_id)
        if success:
            self.logger.info(f"User {user_id} removed vote for option {option_id} in voting {voting_id}")
            return True, "Голос отменен"
        else:
            return False, "Ошибка при отмене голоса"
    
    def get_voting_stats(self, voting_id: int) -> Optional[dict]:
        """Получить статистику голосования"""
        voting = self.db.get_voting(voting_id)
        if not voting:
            return None
        
        # Получаем всех пользователей из базы данных (включая новых друзей)
        total_users = len(self.db.get_all_users())
        voted_users = len(voting.get_voted_users())
        
        stats = {
            'voting_id': voting_id,
            'title': voting.title,
            'total_users': total_users,
            'voted_users': voted_users,
            'options': []
        }
        
        for option in voting.options:
            votes_for_option = voting.get_votes_for_option(option.option_id)
            stats['options'].append({
                'option_id': option.option_id,
                'description': option.description,
                'date': option.date,
                'votes_count': len(votes_for_option),
                'voters': [vote.user_id for vote in votes_for_option]
            })
        
        return stats
    
    def get_non_voted_users(self, voting_id: int, all_chat_members: List[User]) -> List[User]:
        """Получить пользователей, которые не проголосовали"""
        voting = self.db.get_voting(voting_id)
        if not voting:
            return []
        
        voted_user_ids = voting.get_voted_users()
        return [user for user in all_chat_members if user.user_id not in voted_user_ids]
    
    def format_voting_message(self, voting_id: int) -> str:
        """Форматировать сообщение с результатами голосования"""
        stats = self.get_voting_stats(voting_id)
        if not stats:
            return "Голосование не найдено"
        
        message = f"🗳 **{stats['title']}**\n\n"
        
        for option in stats['options']:
            message += f"{option['description']}: {option['votes_count']} голосов\n"
        
        message += f"\n📊 Проголосовало: {stats['voted_users']}/{stats['total_users']}"
        
        return message
    
    def get_active_voting(self, chat_id: int) -> Optional[Voting]:
        """Получить активное голосование в чате"""
        return self.db.get_active_voting_by_chat(chat_id)
    
    def close_voting(self, voting_id: int) -> Optional[dict]:
        """Завершить голосование и получить результаты"""
        voting = self.db.get_voting(voting_id)
        if not voting:
            return None
        
        if voting.status != VoteStatus.ACTIVE:
            return None
        
        # Обновляем статус голосования на закрытое
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE votings SET status = 'closed' WHERE voting_id = ?
            """, (voting_id,))
            conn.commit()
        
        # Получаем топ-3 результата
        stats = self.get_voting_stats(voting_id)
        if not stats:
            return None
        
        # Сортируем опции по количеству голосов
        sorted_options = sorted(stats['options'], key=lambda x: x['votes_count'], reverse=True)
        top_3 = sorted_options[:3]
        
        return {
            'title': stats['title'],
            'total_users': stats['total_users'],
            'voted_users': stats['voted_users'],
            'top_3': top_3,
            'all_options': sorted_options
        }
    
    def get_detailed_results(self, voting_id: int) -> Optional[dict]:
        """Получить детальные результаты голосования с именами пользователей"""
        voting = self.db.get_voting(voting_id)
        if not voting:
            return None
        
        stats = self.get_voting_stats(voting_id)
        if not stats:
            return None
        
        detailed_options = []
        for option in stats['options']:
            voters_info = []
            for user_id in option['voters']:
                user = self.db.get_user(user_id)
                if user:
                    voters_info.append({
                        'display_name': user.display_name,
                        'user_id': user_id
                    })
            
            detailed_options.append({
                'option_id': option['option_id'],
                'description': option['description'],
                'date': option['date'],
                'votes_count': option['votes_count'],
                'voters': voters_info
            })
        
        return {
            'title': stats['title'],
            'total_users': stats['total_users'],
            'voted_users': stats['voted_users'],
            'options': detailed_options
        } 