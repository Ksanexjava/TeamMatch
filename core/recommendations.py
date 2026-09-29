from core.matching import compatibility


def build_feed(me, all_profiles, swiped_ids=()):
    """Возвращает ленту — список словарей {profile, score, details},
    отсортированный от самых подходящих к наименее подходящим.

    Исключает самого пользователя и тех, кого он уже свайпал (swiped_ids).
    """
    swiped = set(swiped_ids)
    feed = []
    for profile in all_profiles:
        if profile["user_id"] == me["user_id"]:
            continue   
        if profile["user_id"] in swiped:
            continue 
        points, details = compatibility(me, profile)
        feed.append({"profile": profile, "score": points, "details": details})

    feed.sort(key=lambda item: item["score"], reverse=True)
    return feed


def explain(details):
    """Короткая строчка «почему подходит» — по фактам, без ИИ.
    На вход — details из compatibility()."""
    reasons = []
    if details["shared_interests"]:
        reasons.append("общие темы: " + ", ".join(details["shared_interests"]))
    if details["same_goal"]:
        reasons.append("ищете одно и то же")
    if details["complementary_roles"]:
        reasons.append("роли дополняют друг друга")
    if details["same_city"]:
        reasons.append("один город")
    return " · ".join(reasons) if reasons else "пока мало общего"
