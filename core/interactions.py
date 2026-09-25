# core/interactions.py
# Логика лайков и мэтчей — то самое «лайки / мэтчи / уведомления / мои мэтчи».
# Чистые функции над списком лайков. В боте лайки берутся из базы (зона Романа),
# здесь — из теста. Один лайк — словарь: {"from_id": ..., "to_id": ..., "message": ...}


def liked(likes, from_id, to_id):
    """Лайкнул ли from_id пользователя to_id."""
    return any(l["from_id"] == from_id and l["to_id"] == to_id for l in likes)


def is_match(likes, a, b):
    """Взаимный ли лайк между a и b (то есть мэтч)."""
    return liked(likes, a, b) and liked(likes, b, a)


def matches_for(likes, me_id):
    """user_id всех, с кем у меня взаимный лайк. Это список для экрана «Мои мэтчи»."""
    i_liked = {l["to_id"] for l in likes if l["from_id"] == me_id}
    liked_me = {l["from_id"] for l in likes if l["to_id"] == me_id}
    return sorted(i_liked & liked_me)


def incoming_likes(likes, me_id, my_swiped_ids=()):
    """Кто лайкнул меня, а я ему ещё не ответил — для уведомления «тебя лайкнули».
    my_swiped_ids — те, кого я уже свайпнул (чтобы не показывать повторно)."""
    swiped = set(my_swiped_ids)
    return [l for l in likes if l["to_id"] == me_id and l["from_id"] not in swiped]
