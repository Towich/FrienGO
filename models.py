from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Set
from enum import Enum


class VoteStatus(Enum):
    ACTIVE = "active"
    CLOSED = "closed"


@dataclass
class User:
    """Модель пользователя"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    @property
    def display_name(self) -> str:
        """Возвращает отображаемое имя пользователя"""
        if self.first_name:
            return f"{self.first_name} {self.last_name or ''}".strip()
        return self.username or f"User_{self.user_id}"


@dataclass
class VoteOption:
    """Опция голосования (дата выходного дня)"""
    option_id: int
    voting_id: int
    date: date
    description: str
    
    @classmethod
    def create_from_date(cls, option_id: int, voting_id: int, date: date) -> 'VoteOption':
        """Создает опцию из даты"""
        weekday_names = {
            5: "Суббота",
            6: "Воскресенье"
        }
        weekday = weekday_names.get(date.weekday(), "День")
        description = f"{weekday} {date.strftime('%d.%m.%Y')}"
        return cls(option_id, voting_id, date, description)


@dataclass
class Vote:
    """Голос пользователя за опцию"""
    vote_id: int
    user_id: int
    option_id: int
    voting_id: int
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Voting:
    """Голосование"""
    voting_id: int
    chat_id: int
    message_id: Optional[int]
    title: str
    created_at: datetime
    status: VoteStatus = VoteStatus.ACTIVE
    options: List[VoteOption] = field(default_factory=list)
    votes: List[Vote] = field(default_factory=list)
    
    def get_user_votes(self, user_id: int) -> List[Vote]:
        """Получает все голоса пользователя"""
        return [vote for vote in self.votes if vote.user_id == user_id]
    
    def get_votes_for_option(self, option_id: int) -> List[Vote]:
        """Получает все голоса за опцию"""
        return [vote for vote in self.votes if vote.option_id == option_id]
    
    def get_voted_users(self) -> Set[int]:
        """Получает множество ID пользователей, которые проголосовали"""
        return {vote.user_id for vote in self.votes}
    
    def has_user_voted_for_option(self, user_id: int, option_id: int) -> bool:
        """Проверяет, голосовал ли пользователь за конкретную опцию"""
        return any(vote.user_id == user_id and vote.option_id == option_id 
                  for vote in self.votes)


@dataclass
class PingSchedule:
    """Расписание пингов для голосования"""
    schedule_id: int
    voting_id: int
    ping_24h_at: datetime
    ping_48h_at: datetime
    ping_72h_at: datetime
    is_24h_sent: bool = False
    is_48h_sent: bool = False
    is_72h_sent: bool = False 