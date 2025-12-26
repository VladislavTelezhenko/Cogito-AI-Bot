# Тесты приоритетов Celery задач

import pytest

pytestmark = pytest.mark.celery


def test_get_priority_admin():
    # Админ получает наивысший приоритет
    from backend.main import get_priority

    priority = get_priority("admin")
    assert priority == 0


def test_get_priority_ultra():
    # Ultra получает приоритет 1
    from backend.main import get_priority

    priority = get_priority("ultra")
    assert priority == 1


def test_get_priority_premium():
    # Premium получает приоритет 2
    from backend.main import get_priority

    priority = get_priority("premium")
    assert priority == 2


def test_get_priority_free():
    # Free получает приоритет 3
    from backend.main import get_priority

    priority = get_priority("free")
    assert priority == 3


def test_get_priority_basic():
    # Basic получает приоритет 4
    from backend.main import get_priority

    priority = get_priority("basic")
    assert priority == 4


def test_get_priority_unknown_tier():
    # Неизвестный тариф получает приоритет по умолчанию
    from backend.main import get_priority

    priority = get_priority("nonexistent_tier")
    assert priority == 4


def test_priorities_are_sorted_correctly():
    # Приоритеты идут по возрастанию от admin к basic
    from backend.main import get_priority

    tiers = ["admin", "ultra", "premium", "free", "basic"]
    priorities = [get_priority(tier) for tier in tiers]

    # Проверяем что приоритеты возрастают
    assert priorities == sorted(priorities)


def test_admin_has_highest_priority():
    # Админ имеет самый высокий приоритет (минимальное число)
    from backend.main import get_priority

    all_tiers = ["admin", "ultra", "premium", "free", "basic"]
    admin_priority = get_priority("admin")

    for tier in all_tiers:
        assert admin_priority <= get_priority(tier)