#!/usr/bin/env python3
"""
Скрипт для запуска всех тестов FrienGO бота
"""

import unittest
import sys
import os

# Добавляем корневую папку проекта в путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_all_tests():
    """Запустить все тесты"""
    # Находим все тестовые модули
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(__file__)
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Возвращаем код результата
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    print("🧪 Запуск тестов FrienGO бота...\n")
    exit_code = run_all_tests()
    
    if exit_code == 0:
        print("\n✅ Все тесты прошли успешно!")
    else:
        print("\n❌ Некоторые тесты не прошли!")
    
    sys.exit(exit_code) 