import sqlite3
import logging
from datetime import datetime, date
from typing import List, Optional, Set
from contextlib import contextmanager

from models import User, Voting, VoteOption, Vote, VoteStatus, PingSchedule


class DatabaseManager:
    """Менеджер базы данных для работы с SQLite"""
    
    def __init__(self, db_path: str = "friendgo.db"):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для подключения к БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            self.logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT
                )
            """)
            
            # Таблица голосований
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS votings (
                    voting_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active'
                )
            """)
            
            # Таблица опций голосования
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vote_options (
                    option_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    voting_id INTEGER NOT NULL,
                    date DATE,
                    description TEXT NOT NULL,
                    FOREIGN KEY (voting_id) REFERENCES votings (voting_id)
                )
            """)
            
            # Таблица голосов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    option_id INTEGER NOT NULL,
                    voting_id INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (option_id) REFERENCES vote_options (option_id),
                    FOREIGN KEY (voting_id) REFERENCES votings (voting_id)
                )
            """)
            
            # Таблица расписания пингов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ping_schedules (
                    schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    voting_id INTEGER NOT NULL,
                    ping_24h_at TIMESTAMP NOT NULL,
                    ping_48h_at TIMESTAMP NOT NULL,
                    ping_72h_at TIMESTAMP NOT NULL,
                    is_24h_sent BOOLEAN DEFAULT FALSE,
                    is_48h_sent BOOLEAN DEFAULT FALSE,
                    is_72h_sent BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (voting_id) REFERENCES votings (voting_id)
                )
            """)
            
            conn.commit()
            self.logger.info("Database initialized successfully")
    
    # User methods
    def save_user(self, user: User) -> User:
        """Сохранить пользователя в БД"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (user.user_id, user.username, user.first_name, user.last_name))
            conn.commit()
            return user
    
    def get_user(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return User(
                    user_id=row['user_id'],
                    username=row['username'],
                    first_name=row['first_name'],
                    last_name=row['last_name']
                )
            return None
    
    def get_chat_users(self, chat_id: int) -> List[User]:
        """Получить всех пользователей чата (кто когда-либо голосовал)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT u.* FROM users u
                JOIN votes v ON u.user_id = v.user_id
                JOIN votings vt ON v.voting_id = vt.voting_id
                WHERE vt.chat_id = ?
            """, (chat_id,))
            return [User(
                user_id=row['user_id'],
                username=row['username'],
                first_name=row['first_name'],
                last_name=row['last_name']
            ) for row in cursor.fetchall()]
    
    def get_all_users(self) -> List[User]:
        """Получить всех пользователей из базы данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users ORDER BY user_id")
            return [User(
                user_id=row['user_id'],
                username=row['username'],
                first_name=row['first_name'],
                last_name=row['last_name']
            ) for row in cursor.fetchall()]
    
    # Voting methods
    def create_voting(self, voting: Voting) -> Voting:
        """Создать новое голосование"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO votings (chat_id, message_id, title, created_at, status)
                VALUES (?, ?, ?, ?, ?)
            """, (voting.chat_id, voting.message_id, voting.title, 
                  voting.created_at, voting.status.value))
            
            voting_id = cursor.lastrowid
            voting.voting_id = voting_id
            
            # Сохранить опции
            for option in voting.options:
                option.voting_id = voting_id
                cursor.execute("""
                    INSERT INTO vote_options (voting_id, date, description)
                    VALUES (?, ?, ?)
                """, (option.voting_id, option.date, option.description))
                option.option_id = cursor.lastrowid
            
            conn.commit()
            return voting
    
    def get_voting(self, voting_id: int) -> Optional[Voting]:
        """Получить голосование по ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Получить само голосование
            cursor.execute("SELECT * FROM votings WHERE voting_id = ?", (voting_id,))
            voting_row = cursor.fetchone()
            if not voting_row:
                return None
            
            # Получить опции
            cursor.execute("SELECT * FROM vote_options WHERE voting_id = ?", (voting_id,))
            options = []
            for row in cursor.fetchall():
                date_value = None
                if row['date']:
                    date_value = datetime.strptime(row['date'], '%Y-%m-%d').date()
                options.append(VoteOption(
                    option_id=row['option_id'],
                    voting_id=row['voting_id'],
                    date=date_value,
                    description=row['description']
                ))
            
            # Получить голоса
            cursor.execute("SELECT * FROM votes WHERE voting_id = ?", (voting_id,))
            votes = [Vote(
                vote_id=row['vote_id'],
                user_id=row['user_id'],
                option_id=row['option_id'],
                voting_id=row['voting_id'],
                created_at=datetime.fromisoformat(row['created_at'])
            ) for row in cursor.fetchall()]
            
            return Voting(
                voting_id=voting_row['voting_id'],
                chat_id=voting_row['chat_id'],
                message_id=voting_row['message_id'],
                title=voting_row['title'],
                created_at=datetime.fromisoformat(voting_row['created_at']),
                status=VoteStatus(voting_row['status']),
                options=options,
                votes=votes
            )
    
    def get_active_voting_by_chat(self, chat_id: int) -> Optional[Voting]:
        """Получить активное голосование в чате"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT voting_id FROM votings 
                WHERE chat_id = ? AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """, (chat_id,))
            row = cursor.fetchone()
            if row:
                return self.get_voting(row['voting_id'])
            return None
    
    def get_last_closed_voting_message_id(self, chat_id: int) -> Optional[int]:
        """Получить message_id последнего закрытого голосования в чате"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT message_id FROM votings 
                WHERE chat_id = ? AND status = 'closed' AND message_id IS NOT NULL
                ORDER BY created_at DESC LIMIT 1
            """, (chat_id,))
            row = cursor.fetchone()
            if row:
                return row['message_id']
            return None
    
    def update_voting_message_id(self, voting_id: int, message_id: int):
        """Обновить ID сообщения голосования"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE votings SET message_id = ? WHERE voting_id = ?
            """, (message_id, voting_id))
            conn.commit()
    
    # Vote methods
    def add_vote(self, vote: Vote) -> Vote:
        """Добавить голос"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO votes (user_id, option_id, voting_id, created_at)
                VALUES (?, ?, ?, ?)
            """, (vote.user_id, vote.option_id, vote.voting_id, vote.created_at))
            vote.vote_id = cursor.lastrowid
            conn.commit()
            return vote
    
    def remove_vote(self, user_id: int, option_id: int, voting_id: int) -> bool:
        """Удалить голос пользователя за опцию"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM votes 
                WHERE user_id = ? AND option_id = ? AND voting_id = ?
            """, (user_id, option_id, voting_id))
            conn.commit()
            return cursor.rowcount > 0
    
    # Ping schedule methods
    def create_ping_schedule(self, schedule: PingSchedule) -> PingSchedule:
        """Создать расписание пингов"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ping_schedules 
                (voting_id, ping_24h_at, ping_48h_at, ping_72h_at, 
                 is_24h_sent, is_48h_sent, is_72h_sent)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (schedule.voting_id, schedule.ping_24h_at, schedule.ping_48h_at,
                  schedule.ping_72h_at, schedule.is_24h_sent, 
                  schedule.is_48h_sent, schedule.is_72h_sent))
            schedule.schedule_id = cursor.lastrowid
            conn.commit()
            return schedule
    
    def get_pending_pings(self, current_time: datetime) -> List[PingSchedule]:
        """Получить ожидающие отправки пинги"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ping_schedules WHERE
                (ping_24h_at <= ? AND is_24h_sent = FALSE) OR
                (ping_48h_at <= ? AND is_48h_sent = FALSE) OR
                (ping_72h_at <= ? AND is_72h_sent = FALSE)
            """, (current_time, current_time, current_time))
            
            return [PingSchedule(
                schedule_id=row['schedule_id'],
                voting_id=row['voting_id'],
                ping_24h_at=datetime.fromisoformat(row['ping_24h_at']),
                ping_48h_at=datetime.fromisoformat(row['ping_48h_at']),
                ping_72h_at=datetime.fromisoformat(row['ping_72h_at']),
                is_24h_sent=bool(row['is_24h_sent']),
                is_48h_sent=bool(row['is_48h_sent']),
                is_72h_sent=bool(row['is_72h_sent'])
            ) for row in cursor.fetchall()]
    
    def mark_ping_sent(self, schedule_id: int, ping_type: str):
        """Отметить пинг как отправленный"""
        column = f"is_{ping_type}_sent"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                UPDATE ping_schedules SET {column} = TRUE WHERE schedule_id = ?
            """, (schedule_id,))
            conn.commit() 