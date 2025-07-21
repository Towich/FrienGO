"""Тесты для сервиса голосования"""

import unittest
import tempfile
import os
from datetime import date, timedelta
from unittest.mock import patch

from database import DatabaseManager
from voting import VotingService
from models import User, VoteStatus


class TestVotingService(unittest.TestCase):
    """Тесты для VotingService"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        # Создаем временную БД для тестов
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        self.db = DatabaseManager(self.temp_db.name)
        self.voting_service = VotingService(self.db)
    
    def tearDown(self):
        """Очистка после тестов"""
        os.unlink(self.temp_db.name)
    
    def test_generate_weekend_dates(self):
        """Тест генерации выходных дней"""
        # Фиксированная дата - понедельник
        start_date = date(2024, 1, 1)  # Понедельник
        weekends = self.voting_service.generate_weekend_dates(start_date, weeks=2)
        
        # Должно быть 4 дня (2 недели * 2 дня)
        self.assertEqual(len(weekends), 4)
        
        # Первая суббота должна быть 6 января
        self.assertEqual(weekends[0], date(2024, 1, 6))
        # Первое воскресенье должно быть 7 января
        self.assertEqual(weekends[1], date(2024, 1, 7))
        # Вторая суббота должна быть 13 января
        self.assertEqual(weekends[2], date(2024, 1, 13))
        # Второе воскресенье должно быть 14 января
        self.assertEqual(weekends[3], date(2024, 1, 14))
    
    def test_generate_weekend_dates_from_saturday(self):
        """Тест генерации выходных дней начиная с субботы"""
        start_date = date(2024, 1, 6)  # Суббота
        weekends = self.voting_service.generate_weekend_dates(start_date, weeks=1)
        
        self.assertEqual(len(weekends), 2)
        self.assertEqual(weekends[0], date(2024, 1, 6))  # Эта суббота
        self.assertEqual(weekends[1], date(2024, 1, 7))  # Это воскресенье
    
    def test_create_voting(self):
        """Тест создания голосования"""
        chat_id = 123
        voting = self.voting_service.create_voting(chat_id, "Тестовое голосование")
        
        self.assertIsNotNone(voting.voting_id)
        self.assertEqual(voting.chat_id, chat_id)
        self.assertEqual(voting.title, "Тестовое голосование")
        self.assertEqual(voting.status, VoteStatus.ACTIVE)
        self.assertEqual(len(voting.options), 8)  # 4 недели * 2 дня
    
    def test_create_voting_with_existing_active(self):
        """Тест создания голосования при наличии активного"""
        chat_id = 123
        
        # Создаем первое голосование
        self.voting_service.create_voting(chat_id)
        
        # Пытаемся создать второе - должна быть ошибка
        with self.assertRaises(ValueError) as context:
            self.voting_service.create_voting(chat_id)
        
        self.assertIn("уже есть активное голосование", str(context.exception))
    
    def test_vote_for_option(self):
        """Тест голосования за опцию"""
        chat_id = 123
        user_id = 456
        
        # Создаем голосование
        voting = self.voting_service.create_voting(chat_id)
        option_id = voting.options[0].option_id
        
        # Голосуем
        success, message = self.voting_service.vote_for_option(user_id, option_id, voting.voting_id)
        
        self.assertTrue(success)
        self.assertEqual(message, "Голос засчитан!")
        
        # Проверяем, что голос сохранен
        updated_voting = self.db.get_voting(voting.voting_id)
        self.assertTrue(updated_voting.has_user_voted_for_option(user_id, option_id))
    
    def test_vote_for_same_option_twice(self):
        """Тест повторного голосования за ту же опцию"""
        chat_id = 123
        user_id = 456
        
        voting = self.voting_service.create_voting(chat_id)
        option_id = voting.options[0].option_id
        
        # Первый голос
        self.voting_service.vote_for_option(user_id, option_id, voting.voting_id)
        
        # Второй голос за ту же опцию
        success, message = self.voting_service.vote_for_option(user_id, option_id, voting.voting_id)
        
        self.assertFalse(success)
        self.assertIn("уже голосовали", message)
    
    def test_remove_vote(self):
        """Тест отмены голоса"""
        chat_id = 123
        user_id = 456
        
        voting = self.voting_service.create_voting(chat_id)
        option_id = voting.options[0].option_id
        
        # Сначала голосуем
        self.voting_service.vote_for_option(user_id, option_id, voting.voting_id)
        
        # Затем отменяем голос
        success, message = self.voting_service.remove_vote(user_id, option_id, voting.voting_id)
        
        self.assertTrue(success)
        self.assertEqual(message, "Голос отменен")
        
        # Проверяем, что голос удален
        updated_voting = self.db.get_voting(voting.voting_id)
        self.assertFalse(updated_voting.has_user_voted_for_option(user_id, option_id))
    
    def test_remove_nonexistent_vote(self):
        """Тест отмены несуществующего голоса"""
        chat_id = 123
        user_id = 456
        
        voting = self.voting_service.create_voting(chat_id)
        option_id = voting.options[0].option_id
        
        # Пытаемся отменить голос, не проголосовав
        success, message = self.voting_service.remove_vote(user_id, option_id, voting.voting_id)
        
        self.assertFalse(success)
        self.assertIn("не голосовали", message)
    
    def test_get_voting_stats(self):
        """Тест получения статистики голосования"""
        chat_id = 123
        user_id1 = 456
        user_id2 = 789
        
        voting = self.voting_service.create_voting(chat_id)
        option_id = voting.options[0].option_id
        
        # Добавляем пользователей в БД
        user1 = User(user_id1, "user1", "User", "One")
        user2 = User(user_id2, "user2", "User", "Two")
        self.db.save_user(user1)
        self.db.save_user(user2)
        
        # Голосуем первым пользователем
        self.voting_service.vote_for_option(user_id1, option_id, voting.voting_id)
        
        stats = self.voting_service.get_voting_stats(voting.voting_id)
        
        self.assertIsNotNone(stats)
        self.assertEqual(stats['voting_id'], voting.voting_id)
        self.assertEqual(stats['voted_users'], 1)
        self.assertEqual(len(stats['options']), 8)
        
        # Проверяем статистику первой опции
        first_option_stats = stats['options'][0]
        self.assertEqual(first_option_stats['votes_count'], 1)
        self.assertIn(user_id1, first_option_stats['voters'])
    
    def test_get_non_voted_users(self):
        """Тест получения непроголосовавших пользователей"""
        chat_id = 123
        user_id1 = 456
        user_id2 = 789
        
        voting = self.voting_service.create_voting(chat_id)
        option_id = voting.options[0].option_id
        
        user1 = User(user_id1, "user1", "User", "One")
        user2 = User(user_id2, "user2", "User", "Two")
        all_users = [user1, user2]
        
        # Голосует только первый пользователь
        self.voting_service.vote_for_option(user_id1, option_id, voting.voting_id)
        
        non_voted = self.voting_service.get_non_voted_users(voting.voting_id, all_users)
        
        self.assertEqual(len(non_voted), 1)
        self.assertEqual(non_voted[0].user_id, user_id2)
    
    def test_format_voting_message(self):
        """Тест форматирования сообщения голосования"""
        chat_id = 123
        user_id = 456
        
        voting = self.voting_service.create_voting(chat_id, "Тест")
        option_id = voting.options[0].option_id
        
        # Голосуем
        self.voting_service.vote_for_option(user_id, option_id, voting.voting_id)
        
        message = self.voting_service.format_voting_message(voting.voting_id)
        
        self.assertIn("🗳 **Тест**", message)
        self.assertIn("📊 Проголосовало: 1/1", message)
        self.assertIn("1 голосов", message)  # Должен быть счетчик голосов


if __name__ == "__main__":
    unittest.main() 