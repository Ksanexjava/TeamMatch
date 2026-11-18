from aiogram.fsm.state import State, StatesGroup


class Form(StatesGroup):
    """Шаги анкеты — те же, что в боте MAX."""
    name = State()
    photo = State()
    university = State()
    degree = State()
    degree_med = State()
    course = State()
    course_manual = State()
    direction = State()
    city = State()
    role = State()
    looking_for = State()
    interests = State()
    about = State()
    github = State()
    username = State()
    confirm = State()


class FeedFlow(StatesGroup):
    writing_message = State()


class LinkFlow(StatesGroup):
    code = State()
