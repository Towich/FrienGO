"""Тесты для моделей данных"""

import unittest
from datetime import datetime, date
from models import User, VoteOption, Vote, Voting, VoteStatus, PingSchedule


class TestUser(unittest.TestCase):
    """Тесты для модели User"""
    
    def test_user_creation(self):
        """Тест создания пользователя"""
        user = User(
            user_id=123,
            username="testuser",
            first_name="Тест",
            last_name="Пользователь"
        )
        
        self.assertEqual(user.user_id, 123)
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.first_name, "Тест")
        self.assertEqual(user.last_name, "Пользователь")
    
    def test_display_name_with_full_name(self):
        """Тест отображаемого имени с полным именем"""
        user = User(
            user_id=123,
            username="testuser",
            first_name="Тест",
            last_name="Пользователь"
        )
        
        self.assertEqual(user.display_name, "Тест Пользователь")
    
    def test_display_name_with_first_name_only(self):
        """Тест отображаемого имени только с именем"""
        user = User(
            user_id=123,
            username="testuser",
            first_name="Тест",
            last_name=None
        )
        
        self.assertEqual(user.display_name, "Тест")
    
    def test_display_name_with_username_only(self):
        """Тест отображаемого имени только с username"""
        user = User(
            user_id=123,
            username="testuser",
            first_name=None,
            last_name=None
        )
        
        self.assertEqual(user.display_name, "testuser")
    
    def test_display_name_fallback(self):
        """Тест fallback для отображаемого имени"""
        user = User(
            user_id=123,
            username=None,
            first_name=None,
            last_name=None
        )
        
        self.assertEqual(user.display_name, "User_123")


class TestVoteOption(unittest.TestCase):
    """Тесты для модели VoteOption"""
    
    def test_vote_option_creation(self):
        """Тест создания опции голосования"""
        option = VoteOption(
            option_id=1,
            voting_id=1,
            date=date(2024, 1, 6),  # Суббота
            description="Суббота 06.01.2024"
        )
        
        self.assertEqual(option.option_id, 1)
        self.assertEqual(option.voting_id, 1)
        self.assertEqual(option.date, date(2024, 1, 6))
        self.assertEqual(option.description, "Суббота 06.01.2024")
    
    def test_create_from_date_saturday(self):
        """Тест создания опции из даты (суббота)"""
        test_date = date(2024, 1, 6)  # Суббота
        option = VoteOption.create_from_date(1, 1, test_date)
        
        self.assertEqual(option.option_id, 1)
        self.assertEqual(option.voting_id, 1)
        self.assertEqual(option.date, test_date)
        self.assertEqual(option.description, "Суббота 06.01.2024")
    
    def test_create_from_date_sunday(self):
        """Тест создания опции из даты (воскресенье)"""
        test_date = date(2024, 1, 7)  # Воскресенье
        option = VoteOption.create_from_date(1, 1, test_date)
        
        self.assertEqual(option.option_id, 1)
        self.assertEqual(option.voting_id, 1)
        self.assertEqual(option.date, test_date)
        self.assertEqual(option.description, "Воскресенье 07.01.2024")


class TestVoting(unittest.TestCase):
    """Тесты для модели Voting"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.voting = Voting(
            voting_id=1,
            chat_id=123,
            message_id=456,
            title="Тестовое голосование",
            created_at=datetime.now(),
            status=VoteStatus.ACTIVE
        )
        
        # Добавляем опции
        self.option1 = VoteOption(1, 1, date(2024, 1, 6), "Суббота 06.01.2024")
        self.option2 = VoteOption(2, 1, date(2024, 1, 7), "Воскресенье 07.01.2024")
        self.voting.options = [self.option1, self.option2]
        
        # Добавляем голоса
        self.vote1 = Vote(1, 100, 1, 1, datetime.now())  # user 100 за option 1
        self.vote2 = Vote(2, 200, 1, 1, datetime.now())  # user 200 за option 1
        self.vote3 = Vote(3, 100, 2, 1, datetime.now())  # user 100 за option 2
        self.voting.votes = [self.vote1, self.vote2, self.vote3]
    
    def test_get_user_votes(self):
        """Тест получения голосов пользователя"""
        user_votes = self.voting.get_user_votes(100)
        self.assertEqual(len(user_votes), 2)
        self.assertIn(self.vote1, user_votes)
        self.assertIn(self.vote3, user_votes)
    
    def test_get_votes_for_option(self):
        """Тест получения голосов за опцию"""
        option_votes = self.voting.get_votes_for_option(1)
        self.assertEqual(len(option_votes), 2)
        self.assertIn(self.vote1, option_votes)
        self.assertIn(self.vote2, option_votes)
    
    def test_get_voted_users(self):
        """Тест получения проголосовавших пользователей"""
        voted_users = self.voting.get_voted_users()
        self.assertEqual(voted_users, {100, 200})
    
    def test_has_user_voted_for_option(self):
        """Тест проверки голоса пользователя за опцию"""
        self.assertTrue(self.voting.has_user_voted_for_option(100, 1))
        self.assertTrue(self.voting.has_user_voted_for_option(100, 2))
        self.assertFalse(self.voting.has_user_voted_for_option(200, 2))


class TestPingSchedule(unittest.TestCase):
    """Тесты для модели PingSchedule"""
    
    def test_ping_schedule_creation(self):
        """Тест создания расписания пингов"""
        now = datetime.now()
        schedule = PingSchedule(
            schedule_id=1,
            voting_id=1,
            ping_24h_at=now,
            ping_48h_at=now,
            ping_72h_at=now
        )
        
        self.assertEqual(schedule.schedule_id, 1)
        self.assertEqual(schedule.voting_id, 1)
        self.assertFalse(schedule.is_24h_sent)
        self.assertFalse(schedule.is_48h_sent)
        self.assertFalse(schedule.is_72h_sent)


if __name__ == "__main__":
    unittest.main() 