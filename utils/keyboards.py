from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from database.models import JobCategory
from localization import I18n

REMOVE = ReplyKeyboardRemove()

# ── Helpers ────────────────────────────────────────────────────────────────

def _btn(text: str, callback_data: str, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data, style=style)

def _url_btn(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)

# Shortcuts
def _ok(text: str, cb: str) -> InlineKeyboardButton:
    return _btn(text, cb, "success")

def _bad(text: str, cb: str) -> InlineKeyboardButton:
    return _btn(text, cb, "danger")

def _nav(text: str, cb: str) -> InlineKeyboardButton:
    return _btn(text, cb, "primary")


# ── Language ───────────────────────────────────────────────────────────────

def lang_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav("🇺🇦 Українська", "lang:uk"),
        _nav("🇷🇺 Русский",    "lang:ru"),
        _nav("🇬🇧 English",    "lang:en"),
    )
    builder.adjust(1)
    return builder.as_markup()


# ── Main menu ──────────────────────────────────────────────────────────────

def main_menu(role, i18n: I18n) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text=i18n("btn_find_jobs")),
        KeyboardButton(text=i18n("btn_create_job")),
    )
    builder.row(
        KeyboardButton(text=i18n("btn_my_jobs")),
        KeyboardButton(text=i18n("btn_my_applications")),
    )
    builder.row(
        KeyboardButton(text=i18n("btn_browse_services")),
        KeyboardButton(text=i18n("btn_my_services")),
    )
    builder.row(
        KeyboardButton(text=i18n("btn_chats")),
        KeyboardButton(text=i18n("btn_reviews")),
    )
    builder.row(
        KeyboardButton(text=i18n("btn_profile")),
        KeyboardButton(text=i18n("btn_dashboard")),
    )
    return builder.as_markup(resize_keyboard=True)


# ── Confirm / Cancel ───────────────────────────────────────────────────────

def confirm_cancel_kb(i18n: I18n, confirm_cb: str = "confirm", cancel_cb: str = "cancel") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_confirm"), confirm_cb),
        _bad(i18n("btn_cancel"), cancel_cb),
    )
    builder.adjust(2)
    return builder.as_markup()


def back_kb(i18n: I18n, callback: str = "back") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_nav(i18n("btn_back"), callback))
    return builder.as_markup()


# ── Categories ─────────────────────────────────────────────────────────────

CATEGORY_CB_MAP = {
    JobCategory.design:       "cat_design",
    JobCategory.programming:  "cat_programming",
    JobCategory.marketing:    "cat_marketing",
    JobCategory.writing:      "cat_writing",
    JobCategory.translation:  "cat_translation",
    JobCategory.video:        "cat_video",
    JobCategory.audio:        "cat_audio",
    JobCategory.data:         "cat_data",
    JobCategory.other:        "cat_other",
}


def categories_kb(i18n: I18n, prefix: str = "category") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat, key in CATEGORY_CB_MAP.items():
        builder.add(_nav(i18n(key), f"{prefix}:{cat.value}"))
    builder.add(_nav(i18n("btn_back"), "back"))
    builder.adjust(2)
    return builder.as_markup()


# ── Job list / pagination ──────────────────────────────────────────────────

def jobs_list_kb(
    jobs: list,
    page: int,
    total_pages: int,
    i18n: I18n,
    prefix: str = "job",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for job in jobs:
        label = f"📌 {job.title[:40]} — ${job.budget:.0f}"
        builder.add(_nav(label, f"{prefix}:{job.id}"))
    builder.adjust(1)

    nav = []
    if page > 1:
        nav.append(_nav(i18n("btn_prev"), f"page:{page-1}"))
    nav.append(_nav(f"{page}/{total_pages}", "noop"))
    if page < total_pages:
        nav.append(_nav(i18n("btn_next"), f"page:{page+1}"))
    if nav:
        builder.row(*nav)

    builder.row(
        _nav(i18n("btn_filters"), "filters"),
        _bad(i18n("btn_clear_filters"), "clear_filters"),
    )
    return builder.as_markup()


# ── Job detail ─────────────────────────────────────────────────────────────

def job_detail_freelancer_kb(job_id: int, i18n: I18n, employer_db_id: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_ok(i18n("btn_apply"), f"apply:{job_id}"))
    if employer_db_id:
        builder.add(_nav(i18n("btn_message_employer"), f"direct_chat:{employer_db_id}:{job_id}"))
        builder.add(_nav(i18n("btn_back"), "jobs_list"))
        builder.adjust(2, 1)
    else:
        builder.add(_nav(i18n("btn_back"), "jobs_list"))
        builder.adjust(1)
    return builder.as_markup()


def job_detail_employer_kb(job_id: int, app_count: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_view_applications", count=app_count), f"job_apps:{job_id}"),
        _nav(i18n("btn_send_invitation"), f"job_invite:{job_id}"),
        _bad(i18n("btn_cancel_job"),      f"cancel_job:{job_id}"),
        _nav(i18n("btn_back"),            "my_jobs"),
    )
    builder.adjust(2, 1, 1)
    return builder.as_markup()


# ── Applications ───────────────────────────────────────────────────────────

def application_actions_kb(app_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_accept_app"),         f"accept_app:{app_id}"),
        _bad(i18n("btn_reject_app"),        f"reject_app:{app_id}"),
        _nav(i18n("btn_message_freelancer"), f"chat_from_app:{app_id}"),
        _nav(i18n("btn_back"),              "back_to_apps"),
    )
    builder.adjust(2)
    return builder.as_markup()


def my_application_kb(app_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _bad(i18n("btn_withdraw_app"), f"withdraw_app:{app_id}"),
        _nav(i18n("btn_back"),         "my_applications"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ── Deal ───────────────────────────────────────────────────────────────────

def deal_employer_kb(deal_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_ok(i18n("btn_fund_escrow", amount=0), f"fund_escrow:{deal_id}"))
    builder.adjust(1)
    return builder.as_markup()


def deal_employer_confirm_kb(deal_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_confirm_work"), f"confirm_work:{deal_id}"),
        _bad(i18n("btn_dispute"),     f"dispute:{deal_id}"),
    )
    builder.adjust(2)
    return builder.as_markup()


def deal_freelancer_kb(deal_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_ok(i18n("btn_submit_work"), f"submit_work:{deal_id}"))
    builder.adjust(1)
    return builder.as_markup()


# ── Payment ────────────────────────────────────────────────────────────────

def payment_method_kb(i18n: I18n, mode: str = "topup") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_top_up_cryptobot"), f"pay_method:{mode}:cryptobot"),
        _nav(i18n("btn_top_up_ton"),       f"pay_method:{mode}:ton"),
        _nav(i18n("btn_back"),             "balance"),
    )
    builder.adjust(2, 1)
    return builder.as_markup()


def cryptobot_pay_kb(pay_url: str, i18n: I18n, invoice_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_url_btn(i18n("btn_pay"), pay_url))
    builder.add(_nav(i18n("btn_check_payment"), f"check_pay:{invoice_id}"))
    builder.adjust(1)
    return builder.as_markup()


def ton_pay_kb(i18n: I18n, check_cb: str, wallet: str = "", nano_tons: int = 0, memo: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if wallet and nano_tons:
        deep_link = f"ton://transfer/{wallet}?amount={nano_tons}&text={memo}"
        builder.add(_url_btn(i18n("tonkeeper_btn"), deep_link))
    builder.add(_nav(i18n("btn_check_payment"), check_cb))
    builder.adjust(1)
    return builder.as_markup()


# ── Reviews ────────────────────────────────────────────────────────────────

def rating_kb(i18n: I18n, deal_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
    for i, label in enumerate(stars, 1):
        builder.add(_ok(label, f"rate:{deal_id}:{i}"))
    builder.adjust(5)
    return builder.as_markup()


def review_text_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_nav(i18n("btn_skip"), "skip_review_text"))
    return builder.as_markup()


# ── Chat ───────────────────────────────────────────────────────────────────

def chats_list_kb(conversations: list, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for conv in conversations:
        label = f"💬 {conv['name']}"
        if conv.get("unread"):
            label += f" 🔴{conv['unread']}"
        builder.add(_nav(label, f"open_chat:{conv['user_id']}:{conv.get('job_id', 0)}"))
    builder.adjust(1)
    return builder.as_markup()


def chat_reply_kb(sender_id: int, job_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_nav(i18n("btn_reply"), f"open_chat:{sender_id}:{job_id}"))
    return builder.as_markup()


# ── Profile ────────────────────────────────────────────────────────────────

def profile_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_edit_name"),   "edit_name"),
        _nav(i18n("btn_change_role"), "change_role"),
        _ok(i18n("btn_top_up"),       "balance"),
        _nav(i18n("btn_withdraw"),    "balance"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ── Help ───────────────────────────────────────────────────────────────────

def help_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_help_jobs"),     "help:jobs"),
        _nav(i18n("btn_help_payments"), "help:payments"),
        _nav(i18n("btn_help_escrow"),   "help:escrow"),
        _nav(i18n("btn_help_docs"),     "help:docs"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ── Chat exit ─────────────────────────────────────────────────────────────

def exit_chat_kb(i18n: I18n) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=i18n("chat_exit"))
    return builder.as_markup(resize_keyboard=True)


# ── Admin ──────────────────────────────────────────────────────────────────

def admin_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_admin_stats"),         "admin:stats"),
        _nav(i18n("btn_admin_referrals"),     "admin:referrals"),
        _nav(i18n("btn_admin_new_broadcast"), "admin:broadcast"),
        _nav(i18n("btn_admin_moderation"),    "admin:moderation"),
        _bad(i18n("btn_admin_disputes"),      "admin:disputes"),
        _nav(i18n("btn_admin_db"),            "admin:db"),
        _nav(i18n("btn_admin_settings"),      "admin:settings"),
    )
    builder.adjust(2)
    return builder.as_markup()


def admin_settings_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_set_service_promo_price"), "admin:set_service_promo_price"),
        _ok(i18n("btn_admin_verify_user"),        "admin:verify_user"),
        _nav(i18n("btn_back"),                    "admin_back"),
    )
    builder.adjust(1)
    return builder.as_markup()


def admin_moderation_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _bad(i18n("btn_admin_ban"),   "admin:ban"),
        _ok(i18n("btn_admin_unban"),  "admin:unban"),
        _nav(i18n("btn_back"),        "admin_back"),
    )
    builder.adjust(2)
    return builder.as_markup()


def admin_stats_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_users_chart"),   "admin:stats_users_chart"),
        _nav(i18n("btn_revenue_chart"), "admin:stats_revenue_chart"),
        _nav(i18n("btn_back"),          "admin_back"),
    )
    builder.adjust(2)
    return builder.as_markup()


def admin_referrals_kb(links: list, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for link in links:
        builder.add(_nav(
            f"🔗 {link.name} ({link.users_count} users)",
            "admin:referral_chart",
        ))
    builder.add(
        _ok(i18n("btn_create_referral"),  "admin:create_referral"),
        _nav(i18n("btn_referral_chart"),  "admin:referral_chart"),
        _nav(i18n("btn_back"),            "admin_back"),
    )
    builder.adjust(1)
    return builder.as_markup()


def admin_broadcast_menu_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_broadcast_new"),     "bcast_new"),
        _nav(i18n("btn_broadcast_history"), "bcast_history"),
        _nav(i18n("btn_back"),             "admin_back"),
    )
    builder.adjust(2)
    return builder.as_markup()


def admin_broadcast_type_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_bcast_text"),  "bcast_type:text"),
        _nav(i18n("btn_bcast_photo"), "bcast_type:photo"),
        _nav(i18n("btn_bcast_video"), "bcast_type:video"),
        _nav(i18n("btn_back"),        "admin:broadcast"),
    )
    builder.adjust(3)
    return builder.as_markup()


def admin_broadcast_confirm_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_confirm"),  "bcast_do_send"),
        _bad(i18n("btn_cancel"), "bcast_cancel"),
    )
    builder.adjust(2)
    return builder.as_markup()


def admin_db_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_db_export"), "admin:db_export"),
        _ok(i18n("btn_db_import"),  "admin:db_import"),
        _nav(i18n("btn_back"),      "admin_back"),
    )
    builder.adjust(2)
    return builder.as_markup()


def admin_dispute_kb(deal_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("btn_admin_resolve_employer"),   f"resolve:employer:{deal_id}"),
        _nav(i18n("btn_admin_resolve_freelancer"), f"resolve:freelancer:{deal_id}"),
        _nav(i18n("btn_admin_resolve_split"),      f"resolve:split:{deal_id}"),
        _nav(i18n("btn_admin_view_chat"),          f"admin_dispute_chat:{deal_id}"),
        _nav(i18n("btn_back"),                     "admin:disputes"),
    )
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()


def skip_evidence_kb(i18n: I18n) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=i18n("btn_skip_evidence"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def dispute_guide_kb(i18n: I18n) -> InlineKeyboardMarkup | None:
    url = i18n("dispute_guide_url")
    if not url.startswith("http"):
        return None
    builder = InlineKeyboardBuilder()
    builder.add(_url_btn(i18n("btn_dispute_guide"), url))
    return builder.as_markup()


# ── Invitations ────────────────────────────────────────────────────────────

def invitation_kb(inv_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_accept_invitation"),  f"inv_accept:{inv_id}"),
        _bad(i18n("btn_decline_invitation"), f"inv_decline:{inv_id}"),
    )
    builder.adjust(2)
    return builder.as_markup()


def my_invitations_kb(invitations: list, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for inv in invitations:
        builder.add(_nav(f"📩 {inv.job.title[:35]}", f"inv_view:{inv.id}"))
    builder.adjust(1)
    return builder.as_markup()


def send_invitation_kb(job_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_send_invitation"), f"send_inv:{job_id}"),
        _nav(i18n("btn_back"),           f"ej:{job_id}"),
    )
    builder.adjust(1)
    return builder.as_markup()


# ── Job Promotion ──────────────────────────────────────────────────────────

def job_promotion_kb(job_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_boost"),  f"promote:boost:{job_id}"),
        _ok(i18n("btn_vip"),    f"promote:vip:{job_id}"),
        _nav(i18n("btn_back"), f"ej:{job_id}"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ── Deal extended ──────────────────────────────────────────────────────────

def deal_freelancer_extended_kb(deal_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_submit_work"), f"submit_work:{deal_id}"),
        _bad(i18n("btn_dispute"),    f"freelancer_dispute:{deal_id}"),
    )
    builder.adjust(2)
    return builder.as_markup()


# ── Advanced filters ───────────────────────────────────────────────────────

def filter_advanced_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _nav(i18n("filter_category_btn"), "filter:category"),
        _nav(i18n("filter_keyword_btn"),  "filter:keyword"),
        _nav(i18n("filter_budget_btn"),   "filter:budget"),
        _bad(i18n("btn_clear_filters"),   "clear_filters"),
        _nav(i18n("btn_back"),            "jobs_list"),
    )
    builder.adjust(2, 2, 1)
    return builder.as_markup()


# ── Profile extended ───────────────────────────────────────────────────────

def profile_extended_kb(i18n: I18n, notifications_enabled: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    notif_label = i18n("btn_notifications_off") if notifications_enabled else i18n("btn_notifications_on")
    builder.add(
        _nav(i18n("btn_edit_name"),  "edit_name"),
        _nav(i18n("btn_dashboard"),  "dashboard"),
        _ok(i18n("btn_top_up"),      "balance"),
        _nav(i18n("btn_withdraw"),   "balance"),
        _nav(notif_label,            "toggle_notifications"),
        _nav(i18n("btn_portfolio"),  "portfolio_manage"),
    )
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def portfolio_manage_kb(i18n: I18n, count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if count < 5:
        builder.add(_ok(i18n("btn_add_portfolio"),  "portfolio_add"))
    if count > 0:
        builder.add(_bad(i18n("btn_del_portfolio"), "portfolio_del_last"))
    builder.add(_nav(i18n("btn_back"), "portfolio_back"))
    if count > 0 and count < 5:
        builder.adjust(2, 1)
    else:
        builder.adjust(1)
    return builder.as_markup()


def view_portfolio_kb(user_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_nav(i18n("btn_view_portfolio"), f"view_portfolio:{user_id}"))
    return builder.as_markup()


# ── Welcome docs ──────────────────────────────────────────────────────────

def welcome_docs_kb(lang: str, i18n: I18n) -> InlineKeyboardMarkup:
    from utils.telegraph_links import FAQ_URLS, PRIVACY_URLS
    labels = {
        "uk": ("❓ FAQ", "🔒 Політика конфіденційності"),
        "ru": ("❓ FAQ", "🔒 Политика конфиденциальности"),
        "en": ("❓ FAQ", "🔒 Privacy Policy"),
    }
    faq_label, privacy_label = labels.get(lang, labels["en"])
    builder = InlineKeyboardBuilder()
    builder.row(
        _url_btn(faq_label,     FAQ_URLS.get(lang, FAQ_URLS["en"])),
        _url_btn(privacy_label, PRIVACY_URLS.get(lang, PRIVACY_URLS["en"])),
    )
    return builder.as_markup()


# ── Dashboard ──────────────────────────────────────────────────────────────

def dashboard_kb(i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_nav(i18n("btn_back"), "profile_back"))
    return builder.as_markup()


# ── Services ───────────────────────────────────────────────────────────────

def services_list_kb(services: list, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in services:
        builder.add(_nav(f"💼 {s.title[:35]} — ${s.price:.0f}", f"svc:{s.id}"))
    builder.adjust(1)
    return builder.as_markup()


def my_services_list_kb(services: list, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in services:
        icon = "✅" if s.is_active else "⏸"
        builder.add(_nav(f"{icon} {s.title[:30]}", f"mysvc:{s.id}"))
    builder.adjust(2)
    builder.row(_ok(i18n("btn_create_service"), "svc_create"))
    return builder.as_markup()


def service_detail_kb(service_id: int, seller_id: int, i18n: I18n, is_own: bool = False, is_promoted: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_own:
        builder.add(_nav(i18n("btn_toggle_service"), f"svc_toggle:{service_id}"))
        if not is_promoted:
            builder.add(_ok(i18n("btn_promote_service"), f"svc_promote:{service_id}"))
        builder.add(_nav(i18n("btn_back"), "my_services_back"))
        builder.adjust(1)
    else:
        builder.add(
            _ok(i18n("btn_buy_service"),    f"svc_buy:{service_id}"),
            _nav(i18n("btn_message_seller"), f"direct_chat:{seller_id}:0"),
            _nav(i18n("btn_back"),          "browse_services"),
        )
        builder.adjust(2, 1)
    return builder.as_markup()


def escrow_currency_kb(deal_id: int, usd_amount: float, ton_amount: float, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(f"💵 USD (${usd_amount:.2f})", f"fund_escrow_cur:usd:{deal_id}"),
        _ok(f"◎ TON ({ton_amount:.4f})",   f"fund_escrow_cur:ton:{deal_id}"),
    )
    builder.adjust(2)
    return builder.as_markup()


def service_order_seller_kb(order_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(_ok(i18n("btn_mark_delivered"), f"svc_delivered:{order_id}"))
    return builder.as_markup()


def service_order_buyer_kb(order_id: int, i18n: I18n) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(
        _ok(i18n("btn_confirm_service"),  f"svc_confirm:{order_id}"),
        _bad(i18n("btn_dispute_service"), f"svc_dispute:{order_id}"),
    )
    builder.adjust(2)
    return builder.as_markup()
