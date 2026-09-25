# demo.py
# Локальный тест твоей части — БЕЗ Postgres и БЕЗ MAX.
# Загружает тестовые анкеты и показывает работу ленты, объяснений и мэтчей.
#
# Запуск из корня проекта:  python demo.py

import json

from core.recommendations import build_feed, explain
from core.interactions import matches_for


def load_profiles(path="data/test_profiles.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def show_feed(profiles, me_id, limit=8):
    """Печатает ленту рекомендаций для одного пользователя."""
    me = next(p for p in profiles if p["user_id"] == me_id)
    print(f"\n=== Лента для {me['name']} "
          f"({me['role']}, ищет: {me['looking_for']}, {me['city']}) ===\n")
    for item in build_feed(me, profiles)[:limit]:
        p = item["profile"]
        print(f"  [{item['score']:>2} очк.] {p['name']}, {p['university']}, {p['course']} курс — {p['role']}")
        print(f"           {explain(item['details'])}")


def demo_match(profiles):
    """Показывает, как срабатывает взаимный лайк (мэтч)."""
    a, b = profiles[0], profiles[1]
    likes = [
        {"from_id": a["user_id"], "to_id": b["user_id"], "message": ""},
        {"from_id": b["user_id"], "to_id": a["user_id"], "message": "го в команду!"},
    ]
    print("\n=== Демо мэтчей ===")
    print(f"{a['name']} лайкнул(а) {b['name']}, {b['name']} лайкнул(а) в ответ.")
    partners = matches_for(likes, a["user_id"])
    print(f"Мэтчи для {a['name']}: {partners}  → бот отдаёт username для связи")


if __name__ == "__main__":
    profiles = load_profiles()
    print(f"Загружено тестовых анкет: {len(profiles)}")
    show_feed(profiles, profiles[0]["user_id"])
    demo_match(profiles)
