"""Тесты для менеджера базы данных"""

import unittest
import tempfile
import os
from datetime import datetime, date, timedelta

from database import DatabaseManager
from models import User, Voting, VoteOption, Vote, VoteStatus, PingSchedule


class TestDatabaseManager(unittest.TestCase):
    """Тесты для DatabaseManager"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        # Создаем временную БД для каждого теста
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        self.db = DatabaseManager(self.temp_db.name)
    
    def tearDown(self):
        """Очистка после тестов"""
        os.unlink(self.temp_db.name)
    
    def test_database_initialization(self):
        """Тест инициализации базы данных"""
        # База данных должна создаться без ошибок
        self.assertTrue(os.path.exists(self.temp_db.name))
        
        # Проверяем, что таблицы созданы
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            expected_tables = ['users', 'votings', 'vote_options', 'votes', 'ping_schedules']
            for table in expected_tables:
                self.assertIn(table, tables)
    
    def test_save_and_get_user(self):
        """Тест сохранения и получения пользователя"""
        user = User(
            user_id=123,
            username="testuser",
            first_name="Тест",
            last_name="Пользователь"
        )
        
        # Сохраняем пользователя
        saved_user = self.db.save_user(user)
        self.assertEqual(saved_user.user_id, 123)
        
        # Получаем пользователя
        retrieved_user = self.db.get_user(123)
        self.assertIsNotNone(retrieved_user)
        self.assertEqual(retrieved_user.user_id, 123)
        self.assertEqual(retrieved_user.username, "testuser")
        self.assertEqual(retrieved_user.first_name, "Тест")
        self.assertEqual(retrieved_user.last_name, "Пользователь")
    
    def test_get_nonexistent_user(self):
        """Тест получения несуществующего пользователя"""
        user = self.db.get_user(999)
        self.assertIsNone(user)
    
    def test_create_and_get_voting(self):
        """Тест создания и получения голосования"""
        now = datetime.now()
        voting = Voting(
            voting_id=0,
            chat_id=123,
            message_id=456,
            title="Тестовое голосование",
            created_at=now,
            status=VoteStatus.ACTIVE
        )
        
        # Добавляем опции
        option1 = VoteOption(0, 0, date(2024, 1, 6), "Суббота 06.01.2024")
        option2 = VoteOption(0, 0, date(2024, 1, 7), "Воскресенье 07.01.2024")
        voting.options = [option1, option2]
        
        # Создаем голосование
        created_voting = self.db.create_voting(voting)
        
        self.assertIsNotNone(created_voting.voting_id)
        self.assertEqual(len(created_voting.options), 2)
        
        # Получаем голосование
        retrieved_voting = self.db.get_voting(created_voting.voting_id)
        
        self.assertIsNotNone(retrieved_voting)
        self.assertEqual(retrieved_voting.chat_id, 123)
        self.assertEqual(retrieved_voting.title, "Тестовое голосование")
        self.assertEqual(len(retrieved_voting.options), 2)
        self.assertEqual(len(retrieved_voting.votes), 0)
    
    def test_add_and_remove_vote(self):
        """Тест добавления и удаления голоса"""
        # Создаем пользователя
        user = User(123, "testuser", "Test", "User")
        self.db.save_user(user)
        
        # Создаем голосование
        voting = Voting(0, 456, None, "Test", datetime.now())
        option = VoteOption(0, 0, date(2024, 1, 6), "Test option")
        voting.options = [option]
        created_voting = self.db.create_voting(voting)
        
        option_id = created_voting.options[0].option_id
        
        # Добавляем голос
        vote = Vote(0, 123, option_id, created_voting.voting_id, datetime.now())
        added_vote = self.db.add_vote(vote)
        
        self.assertIsNotNone(added_vote.vote_id)
        
        # Проверяем, что голос сохранен
        retrieved_voting = self.db.get_voting(created_voting.voting_id)
        self.assertEqual(len(retrieved_voting.votes), 1)
        self.assertEqual(retrieved_voting.votes[0].user_id, 123)
        
        # Удаляем голос
        success = self.db.remove_vote(123, option_id, created_voting.voting_id)
        self.assertTrue(success)
        
        # Проверяем, что голос удален
        retrieved_voting = self.db.get_voting(created_voting.voting_id)
        self.assertEqual(len(retrieved_voting.votes), 0)
    
    def test_get_active_voting_by_chat(self):
        """Тест получения активного голосования в чате"""
        # Создаем голосование
        voting = Voting(0, 123, None, "Active voting", datetime.now())
        voting.options = [VoteOption(0, 0, date(2024, 1, 6), "Test option")]
        created_voting = self.db.create_voting(voting)
        
        # Получаем активное голосование
        active_voting = self.db.get_active_voting_by_chat(123)
        
        self.assertIsNotNone(active_voting)
        self.assertEqual(active_voting.voting_id, created_voting.voting_id)
        
        # В другом чате не должно быть активного голосования
        no_voting = self.db.get_active_voting_by_chat(999)
        self.assertIsNone(no_voting)
    
    def test_update_voting_message_id(self):
        """Тест обновления ID сообщения голосования"""
        voting = Voting(0, 123, None, "Test", datetime.now())
        voting.options = [VoteOption(0, 0, date(2024, 1, 6), "Test option")]
        created_voting = self.db.create_voting(voting)
        
        # Обновляем message_id
        self.db.update_voting_message_id(created_voting.voting_id, 789)
        
        # Проверяем обновление
        updated_voting = self.db.get_voting(created_voting.voting_id)
        self.assertEqual(updated_voting.message_id, 789)
    
    def test_ping_schedule_operations(self):
        """Тест операций с расписанием пингов"""
        # Создаем голосование
        voting = Voting(0, 123, None, "Test", datetime.now())
        voting.options = [VoteOption(0, 0, date(2024, 1, 6), "Test option")]
        created_voting = self.db.create_voting(voting)
        
        # Создаем расписание пингов
        now = datetime.now()
        schedule = PingSchedule(
            schedule_id=0,
            voting_id=created_voting.voting_id,
            ping_24h_at=now + timedelta(hours=24),
            ping_48h_at=now + timedelta(hours=48),
            ping_72h_at=now + timedelta(hours=72)
        )
        
        created_schedule = self.db.create_ping_schedule(schedule)
        self.assertIsNotNone(created_schedule.schedule_id)
        
        # Проверяем получение ожидающих пингов
        future_time = now + timedelta(hours=25)
        pending_pings = self.db.get_pending_pings(future_time)
        
        self.assertEqual(len(pending_pings), 1)
        self.assertEqual(pending_pings[0].voting_id, created_voting.voting_id)
        self.assertFalse(pending_pings[0].is_24h_sent)
        
        # Отмечаем пинг как отправленный
        self.db.mark_ping_sent(created_schedule.schedule_id, "24h")
        
        # Проверяем, что пинг отмечен как отправленный
        updated_pings = self.db.get_pending_pings(future_time)
        # Теперь 24h пинг не должен попадать в список ожидающих
        for ping in updated_pings:
            if ping.schedule_id == created_schedule.schedule_id:
                self.assertTrue(ping.is_24h_sent)
    
    def test_get_chat_users(self):
        """Тест получения пользователей чата"""
        # Создаем пользователей
        user1 = User(123, "user1", "User", "One")
        user2 = User(456, "user2", "User", "Two")
        user3 = User(789, "user3", "User", "Three")
        
        self.db.save_user(user1)
        self.db.save_user(user2)
        self.db.save_user(user3)
        
        # Создаем голосования в разных чатах
        voting1 = Voting(0, 111, None, "Chat 1", datetime.now())
        voting1.options = [VoteOption(0, 0, date(2024, 1, 6), "Test")]
        created_voting1 = self.db.create_voting(voting1)
        
        voting2 = Voting(0, 222, None, "Chat 2", datetime.now())
        voting2.options = [VoteOption(0, 0, date(2024, 1, 6), "Test")]
        created_voting2 = self.db.create_voting(voting2)
        
        # Добавляем голоса
        vote1 = Vote(0, 123, created_voting1.options[0].option_id, created_voting1.voting_id, datetime.now())
        vote2 = Vote(0, 456, created_voting1.options[0].option_id, created_voting1.voting_id, datetime.now())
        vote3 = Vote(0, 789, created_voting2.options[0].option_id, created_voting2.voting_id, datetime.now())
        
        self.db.add_vote(vote1)
        self.db.add_vote(vote2)
        self.db.add_vote(vote3)
        
        # Получаем пользователей чата 111
        chat1_users = self.db.get_chat_users(111)
        chat1_user_ids = {user.user_id for user in chat1_users}
        
        self.assertEqual(len(chat1_users), 2)
        self.assertEqual(chat1_user_ids, {123, 456})
        
        # Получаем пользователей чата 222
        chat2_users = self.db.get_chat_users(222)
        self.assertEqual(len(chat2_users), 1)
        self.assertEqual(chat2_users[0].user_id, 789)
    
    def test_get_last_closed_voting_message_id(self):
        """Тест получения ID сообщения последнего закрытого голосования"""
        chat_id = 123
        
        # Создаем два голосования
        voting1 = Voting(0, chat_id, None, "Test 1", datetime.now())
        voting1.options = [VoteOption(0, 0, date(2024, 1, 6), "Test")]
        created_voting1 = self.db.create_voting(voting1)
        
        voting2 = Voting(0, chat_id, None, "Test 2", datetime.now())
        voting2.options = [VoteOption(0, 0, date(2024, 1, 7), "Test")]
        created_voting2 = self.db.create_voting(voting2)
        
        # Устанавливаем message_id и закрываем голосования
        self.db.update_voting_message_id(created_voting1.voting_id, 100)
        self.db.update_voting_message_id(created_voting2.voting_id, 200)
        
        # Закрываем голосования (меняем статус)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE votings SET status = 'closed' WHERE voting_id = ?", 
                          (created_voting1.voting_id,))
            cursor.execute("UPDATE votings SET status = 'closed' WHERE voting_id = ?", 
                          (created_voting2.voting_id,))
            conn.commit()
        
        # Должно вернуть ID сообщения последнего голосования (voting2)
        last_message_id = self.db.get_last_closed_voting_message_id(chat_id)
        self.assertEqual(last_message_id, 200)
        
        # Тест для чата без голосований
        no_message_id = self.db.get_last_closed_voting_message_id(999)
        self.assertIsNone(no_message_id)


if __name__ == "__main__":
    unittest.main() 