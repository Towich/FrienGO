import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from models import User, PingSchedule
from database import DatabaseManager
from voting import VotingService
from scheduler import PingScheduler


class TestPingScheduler(unittest.TestCase):
    """Тесты для планировщика пингов"""
    
    def setUp(self):
        """Подготовка к тестам"""
        self.db = DatabaseManager(":memory:")
        self.voting_service = VotingService(self.db)
        self.scheduler = PingScheduler(self.db, self.voting_service)
    
    def test_get_ping_message_with_usernames(self):
        """Тест сообщения пинга с пользователями имеющими username"""
        users = [
            User(123, "alice", "Alice", "Smith"),
            User(456, "bob", "Bob", "Jones")
        ]
        
        message = self.scheduler._get_ping_message("24h", users)
        
        self.assertIn("24 часа", message)
        self.assertIn("@alice", message)
        self.assertIn("@bob", message)
        self.assertIn("Ждем голосов от", message)
    
    def test_get_ping_message_without_usernames(self):
        """Тест сообщения пинга с пользователями без username"""
        users = [
            User(123, None, "Alice", "Smith"),
            User(456, None, "Bob", None)
        ]
        
        message = self.scheduler._get_ping_message("48h", users)
        
        self.assertIn("48 часов", message)
        self.assertIn("[Alice Smith](tg://user?id=123)", message)
        self.assertIn("[Bob](tg://user?id=456)", message)
        self.assertIn("Ждем голосов от", message)
    
    def test_get_ping_message_mixed_users(self):
        """Тест сообщения пинга со смешанными типами пользователей"""
        users = [
            User(123, "alice", "Alice", "Smith"),
            User(456, None, "Bob", "Jones"),
            User(789, "charlie", "Charlie", None)
        ]
        
        message = self.scheduler._get_ping_message("72h", users)
        
        self.assertIn("72 часа", message)
        self.assertIn("@alice", message)
        self.assertIn("[Bob Jones](tg://user?id=456)", message)
        self.assertIn("@charlie", message)
    
    def test_get_ping_message_no_users(self):
        """Тест сообщения пинга когда все проголосовали"""
        users = []
        
        message = self.scheduler._get_ping_message("24h", users)
        
        self.assertIn("24 часа", message)
        self.assertIn("Все пользователи уже проголосовали", message)
        self.assertNotIn("Ждем голосов от", message)
    
    def test_ping_message_contains_voting_instructions(self):
        """Тест что сообщение содержит инструкции по голосованию"""
        users = [User(123, "alice", "Alice", "Smith")]
        
        message = self.scheduler._get_ping_message("24h", users)
        
        self.assertIn("Не забудьте проголосовать", message)
        self.assertIn("Нажмите на кнопки", message)


if __name__ == '__main__':
    unittest.main() 