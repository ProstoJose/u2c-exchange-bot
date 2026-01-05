from aiogram.fsm.state import State, StatesGroup


class ExchangeFlow(StatesGroup):
    choose_give = State()
    choose_get = State()
    choose_amount_mode = State()
    enter_amount = State()
    enter_from_location = State()
    enter_to_location = State()
    waiting_for_calc = State()
    enter_contact = State()
    waiting_for_submit = State()
