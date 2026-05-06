from aiogram.fsm.state import State, StatesGroup


class LanguageState(StatesGroup):
    selecting = State()


class RoleState(StatesGroup):
    selecting = State()


class JobCreationState(StatesGroup):
    title = State()
    description = State()
    category = State()
    budget = State()
    deadline = State()
    confirm = State()


class JobFilterState(StatesGroup):
    category = State()
    budget_min = State()
    budget_max = State()
    keyword = State()


class ApplicationState(StatesGroup):
    price = State()
    timeframe = State()
    comment = State()
    confirm = State()


class ProfileEditState(StatesGroup):
    name = State()


class ReviewState(StatesGroup):
    rating = State()
    text = State()


class PaymentState(StatesGroup):
    top_up_amount = State()
    top_up_method = State()
    withdraw_amount = State()
    withdraw_method = State()
    withdraw_address = State()
    withdraw_ton_amount = State()
    withdraw_ton_address = State()


class ChatState(StatesGroup):
    messaging = State()


class WorkSubmitState(StatesGroup):
    description = State()


class DisputeState(StatesGroup):
    reason = State()
    evidence = State()


class InvitationState(StatesGroup):
    select_freelancer = State()
    message = State()
    confirm = State()


class PortfolioState(StatesGroup):
    adding = State()


class ServiceCreationState(StatesGroup):
    title = State()
    description = State()
    category = State()
    price = State()
    confirm = State()


class ServicePromoState(StatesGroup):
    confirm = State()


class AdminState(StatesGroup):
    ban_user_id = State()
    ban_reason = State()
    unban_user_id = State()
    broadcast_message = State()
    dispute_resolve = State()
    dispute_deal_id = State()
    # Referral
    referral_name = State()
    # Broadcast queue
    broadcast_type = State()
    broadcast_text = State()
    broadcast_photo = State()
    broadcast_video = State()
    broadcast_confirm = State()
    # DB import
    db_import_file = State()
    # Settings
    service_promo_price = State()
    # Verify user
    verify_user_id = State()
