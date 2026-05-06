from datetime import datetime

from aiogram.filters import Filter
from aiogram.types import Message

from database.models import JobCategory, JobStatus, DealStatus, ApplicationStatus
from localization import I18n, get_i18n


def btn(*keys: str):
    """Build an aiogram filter that matches a reply-keyboard button in any of the 3 languages."""
    texts: set[str] = set()
    for lang in ("en", "uk", "ru"):
        i18n = get_i18n(lang)
        for key in keys:
            val = i18n(key)
            if val:
                texts.add(val)

    from aiogram import F
    return F.text.in_(texts)


ITEMS_PER_PAGE = 5


def paginate(items: list, page: int) -> tuple[list, int]:
    total = max(1, (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(1, min(page, total))
    start = (page - 1) * ITEMS_PER_PAGE
    return items[start: start + ITEMS_PER_PAGE], total


def format_date(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y")


def format_rating(rating: float, count: int) -> str:
    if count == 0:
        return "—"
    return f"{rating:.1f}"


def category_label(cat: JobCategory, i18n: I18n) -> str:
    key = f"cat_{cat.value}"
    return i18n(key)


def job_status_label(status: JobStatus, i18n: I18n) -> str:
    mapping = {
        JobStatus.open:        "job_status_open",
        JobStatus.in_progress: "job_status_in_progress",
        JobStatus.completed:   "job_status_completed",
        JobStatus.cancelled:   "job_status_cancelled",
        JobStatus.disputed:    "job_status_disputed",
    }
    return i18n(mapping.get(status, "job_status_open"))


def deal_status_label(status: DealStatus, i18n: I18n) -> str:
    mapping = {
        DealStatus.pending_payment: "deal_status_pending",
        DealStatus.escrow_held:     "deal_status_escrow",
        DealStatus.work_submitted:  "deal_status_submitted",
        DealStatus.completed:       "deal_status_completed",
        DealStatus.disputed:        "deal_status_disputed",
        DealStatus.refunded:        "deal_status_refunded",
    }
    return i18n(mapping.get(status, "deal_status_pending"))


def app_status_label(status: ApplicationStatus, i18n: I18n) -> str:
    mapping = {
        ApplicationStatus.pending:   "status_pending",
        ApplicationStatus.accepted:  "status_accepted",
        ApplicationStatus.rejected:  "status_rejected",
        ApplicationStatus.withdrawn: "status_withdrawn",
    }
    return i18n(mapping.get(status, "status_pending"))


def safe_float(value: str) -> float | None:
    try:
        v = float(value.replace(",", "."))
        return v if v > 0 else None
    except ValueError:
        return None
