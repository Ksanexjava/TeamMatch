# tools/generate_test_profiles.py
# Генерирует data/test_profiles.json — 40 тестовых анкет студентов Новосибирска.
# Запуск из корня проекта:  python tools/generate_test_profiles.py

import json
import os
import random

random.seed(42)  # фиксируем, чтобы при каждом запуске анкеты были одинаковыми

FIRST_NAMES = [
    "Анна", "Борис", "Вика", "Глеб", "Даша", "Егор", "Женя", "Иван", "Катя", "Лена",
    "Миша", "Настя", "Олег", "Полина", "Рома", "Соня", "Тимур", "Юля", "Артём", "Вера",
    "Денис", "Зоя", "Кирилл", "Марина", "Никита", "Оля", "Паша", "Саша", "Тоня", "Федя",
]

UNIVERSITIES = ["НГУ", "НГТУ НЭТИ", "НГУЭУ", "СГУПС", "СибГУТИ", "НГПУ", "НГАУ", "СГУГиТ", "НГМУ"]

# Роль -> её типичные интересы. Пересечения интересов между темами дают матчинг.
THEMES = {
    "разработка": ["python", "backend", "api", "git", "базы данных"],
    "ML":         ["ml", "данные", "python", "нейросети", "аналитика"],
    "аналитика":  ["аналитика", "данные", "excel", "sql", "статистика"],
    "дизайн":     ["дизайн", "figma", "ui", "прототипы", "иллюстрация"],
    "маркетинг":  ["маркетинг", "smm", "контент", "реклама", "бренд"],
    "финансы":    ["финансы", "экономика", "excel", "инвестиции", "модели"],
    "питчинг":    ["презентации", "выступления", "сторителлинг", "питч"],
    "менеджмент": ["менеджмент", "планирование", "команда", "agile", "продукт"],
}
ROLES = list(THEMES.keys())
LOOKING_FOR = ["хакатон", "кейс-чемпионат", "олимпиада", "стартап"]
CITIES = ["Новосибирск"] * 8 + ["Бердск", "Академгородок"]  # в основном Новосибирск


def make_profile(i):
    role = random.choice(ROLES)
    interests = random.sample(THEMES[role], k=3)               # 3 интереса из своей темы
    if random.random() < 0.5:                                  # иногда добавляем смежный
        interests.append(random.choice(THEMES[random.choice(ROLES)]))
    interests = sorted(set(interests))
    github = f"https://github.com/user{i:03d}" if role in ("разработка", "ML") else ""
    return {
        "user_id": f"u{i:03d}",
        "username": f"@user{i:03d}",
        "name": random.choice(FIRST_NAMES),
        "university": random.choice(UNIVERSITIES),
        "course": random.randint(1, 4),
        "city": random.choice(CITIES),
        "role": role,
        "looking_for": random.choice(LOOKING_FOR),
        "interests": interests,
        "github": github,
    }


def main():
    profiles = [make_profile(i) for i in range(1, 41)]         # 40 анкет
    os.makedirs("data", exist_ok=True)
    with open("data/test_profiles.json", "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
    print(f"Готово: сохранил {len(profiles)} анкет в data/test_profiles.json")


if __name__ == "__main__":
    main()
