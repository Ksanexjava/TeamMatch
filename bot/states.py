# bot/states.py
# Шаги анкеты. Бот помнит, на каком шаге пользователь (FSM — конечный автомат).

from maxapi.context.state_machine import State, StatesGroup


class ProfileForm(StatesGroup):
    name = State()
    photo = State()
    university = State()
    course = State()
    city = State()
    role = State()
    looking_for = State()
    interests = State()
    about = State()
    github = State()
    contact = State()
    confirm = State()


class FeedFlow(StatesGroup):
    # Зона Миши: пользователь нажал «Лайк + сообщение» и печатает текст.
    writing_message = State()
