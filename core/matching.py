# core/matching.py
# Насколько два профиля подходят друг другу для команды.
# Чистые функции: работают с данными профилей, БЕЗ базы и БЕЗ сети.
#
# Профиль — это словарь. Для матчинга важны поля:
#   role         — роль в команде (строка): аналитика / разработка / дизайн / ...
#   city         — город (строка)
#   looking_for  — что ищет: хакатон / кейс-чемпионат / олимпиада / стартап
#   interests    — список интересов (нормализованный; его готовит часть Романа)


def _norm(text):
    """Приводим строку к нижнему регистру без крайних пробелов — для честного сравнения."""
    return (text or "").strip().lower()


def shared_interests(me, candidate):
    """Общие интересы двух профилей — пересечение их списков interests."""
    mine = {_norm(x) for x in me.get("interests", [])}
    theirs = {_norm(x) for x in candidate.get("interests", [])}
    return mine & theirs


def compatibility(me, candidate):
    """Оценка совместимости. Возвращает (очки, детали).

    Логика подбора:
      • каждый общий интерес   → +3 очка (это главное);
      • одна и та же цель       → +2 (оба ищут хакатон / оба кейс);
      • один город              → +1 (проще собраться очно);
      • РАЗНЫЕ роли             → +1 (команде полезны взаимодополняющие люди).
    """
    shared = shared_interests(me, candidate)
    points = len(shared) * 3

    same_city = bool(_norm(me.get("city")) and _norm(me.get("city")) == _norm(candidate.get("city")))
    if same_city:
        points += 1

    same_goal = bool(_norm(me.get("looking_for")) and _norm(me.get("looking_for")) == _norm(candidate.get("looking_for")))
    if same_goal:
        points += 2

    complementary_roles = _norm(me.get("role")) != _norm(candidate.get("role"))
    if complementary_roles:
        points += 1

    details = {
        "shared_interests": sorted(shared),
        "same_city": same_city,
        "same_goal": same_goal,
        "complementary_roles": complementary_roles,
    }
    return points, details
