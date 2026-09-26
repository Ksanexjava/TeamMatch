from maxapi.context.state_machine import State, StatesGroup


class ProfileForm(StatesGroup):
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
    contact = State()
    confirm = State()


class FeedFlow(StatesGroup):
    writing_message = State()
