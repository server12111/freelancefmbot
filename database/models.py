import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum as SAEnum,
    Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────────

class Language(str, enum.Enum):
    uk = "uk"
    ru = "ru"
    en = "en"


class UserRole(str, enum.Enum):
    freelancer = "freelancer"
    employer = "employer"


class JobCategory(str, enum.Enum):
    design = "design"
    programming = "programming"
    marketing = "marketing"
    writing = "writing"
    translation = "translation"
    video = "video"
    audio = "audio"
    data = "data"
    other = "other"


class JobStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    disputed = "disputed"


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"


class DealStatus(str, enum.Enum):
    pending_payment = "pending_payment"
    escrow_held = "escrow_held"
    work_submitted = "work_submitted"
    completed = "completed"
    disputed = "disputed"
    refunded = "refunded"


class TransactionType(str, enum.Enum):
    top_up = "top_up"
    withdrawal = "withdrawal"
    escrow_hold = "escrow_hold"
    escrow_release = "escrow_release"
    escrow_refund = "escrow_refund"
    platform_fee = "platform_fee"
    promotion = "promotion"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class InvitationStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class MessageType(str, enum.Enum):
    text = "text"
    image = "image"
    file = "file"
    video = "video"


class PromotionType(str, enum.Enum):
    boost = "boost"
    vip = "vip"


# ── Models ─────────────────────────────────────────────────────────────────

class ReferralLink(Base):
    __tablename__ = "referral_links"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    created_by_admin_id = Column(BigInteger, nullable=False)
    users_count = Column(Integer, default=0, nullable=False)
    orders_count = Column(Integer, default=0, nullable=False)
    revenue = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="referral_link")


class BroadcastJob(Base):
    __tablename__ = "broadcast_jobs"

    id = Column(Integer, primary_key=True)
    admin_telegram_id = Column(BigInteger, nullable=False)
    content_type = Column(String(20), nullable=False, default="text")
    text = Column(Text, nullable=True)
    file_id = Column(String(255), nullable=True)
    parse_mode = Column(String(20), default="HTML")
    status = Column(String(20), default="pending", nullable=False)
    total_users = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=False)
    language = Column(SAEnum(Language), default=Language.en, nullable=False)
    role = Column(SAEnum(UserRole), nullable=True)
    balance = Column(Float, default=0.0, nullable=False)
    balance_ton = Column(Float, default=0.0, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    rating = Column(Float, default=0.0, nullable=False)
    rating_count = Column(Integer, default=0, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)
    ban_reason = Column(String(500), nullable=True)
    referral_link_id = Column(Integer, ForeignKey("referral_links.id"), nullable=True)
    # Reputation & stats
    level = Column(String(20), default="newbie", nullable=False)
    completed_orders = Column(Integer, default=0, nullable=False)
    total_earned = Column(Float, default=0.0, nullable=False)
    total_spent = Column(Float, default=0.0, nullable=False)
    # Notifications
    notifications_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    referral_link = relationship("ReferralLink", back_populates="users")
    jobs_created = relationship("Job", back_populates="employer", foreign_keys="Job.employer_id")
    applications = relationship("Application", back_populates="freelancer", foreign_keys="Application.freelancer_id")
    deals_as_employer = relationship("Deal", back_populates="employer", foreign_keys="Deal.employer_id")
    deals_as_freelancer = relationship("Deal", back_populates="freelancer", foreign_keys="Deal.freelancer_id")
    reviews_given = relationship("Review", back_populates="reviewer", foreign_keys="Review.reviewer_id")
    reviews_received = relationship("Review", back_populates="reviewee", foreign_keys="Review.reviewee_id")
    transactions = relationship("Transaction", back_populates="user")
    messages_sent = relationship("Message", back_populates="sender", foreign_keys="Message.sender_id")
    messages_received = relationship("Message", back_populates="receiver", foreign_keys="Message.receiver_id")
    invitations_sent = relationship("Invitation", back_populates="employer", foreign_keys="Invitation.employer_id")
    invitations_received = relationship("Invitation", back_populates="freelancer", foreign_keys="Invitation.freelancer_id")
    portfolio_photos = relationship("PortfolioPhoto", back_populates="user", lazy="selectin", order_by="PortfolioPhoto.created_at")
    services = relationship("Service", back_populates="seller", foreign_keys="Service.seller_id")
    service_orders_as_buyer = relationship("ServiceOrder", back_populates="buyer", foreign_keys="ServiceOrder.buyer_id")
    service_orders_as_seller = relationship("ServiceOrder", back_populates="seller", foreign_keys="ServiceOrder.seller_id")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(SAEnum(JobCategory), nullable=False)
    budget = Column(Float, nullable=False)
    deadline = Column(String(100), nullable=False)
    status = Column(SAEnum(JobStatus), default=JobStatus.open, nullable=False)
    # Promotion
    is_boosted = Column(Boolean, default=False, nullable=False)
    is_vip = Column(Boolean, default=False, nullable=False)
    promoted_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    employer = relationship("User", back_populates="jobs_created", foreign_keys=[employer_id])
    applications = relationship("Application", back_populates="job")
    deal = relationship("Deal", back_populates="job", uselist=False)
    promotions = relationship("Promotion", back_populates="job")
    invitations = relationship("Invitation", back_populates="job")


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    freelancer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    price = Column(Float, nullable=False)
    timeframe = Column(String(100), nullable=False)
    comment = Column(Text, nullable=True)
    status = Column(SAEnum(ApplicationStatus), default=ApplicationStatus.pending, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="applications")
    freelancer = relationship("User", back_populates="applications", foreign_keys=[freelancer_id])
    deal = relationship("Deal", back_populates="application", uselist=False)


class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    freelancer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    platform_fee = Column(Float, nullable=False)
    status = Column(SAEnum(DealStatus), default=DealStatus.pending_payment, nullable=False)
    work_description = Column(Text, nullable=True)
    dispute_reason = Column(Text, nullable=True)
    # Escrow currency
    escrow_currency = Column(String(10), default="usd", nullable=False)
    escrow_ton_amount = Column(Float, nullable=True)
    # Dispute tracking
    dispute_opened_at = Column(DateTime(timezone=True), nullable=True)
    # Auto-release
    submission_time = Column(DateTime(timezone=True), nullable=True)
    auto_release_at = Column(DateTime(timezone=True), nullable=True)
    auto_released = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    job = relationship("Job", back_populates="deal")
    application = relationship("Application", back_populates="deal")
    employer = relationship("User", back_populates="deals_as_employer", foreign_keys=[employer_id])
    freelancer = relationship("User", back_populates="deals_as_freelancer", foreign_keys=[freelancer_id])
    review = relationship("Review", back_populates="deal", uselist=False)
    transactions = relationship("Transaction", back_populates="deal")
    dispute_logs = relationship("DisputeLog", back_populates="deal")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewee_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    deal = relationship("Deal", back_populates="review")
    reviewer = relationship("User", back_populates="reviews_given", foreign_keys=[reviewer_id])
    reviewee = relationship("User", back_populates="reviews_received", foreign_keys=[reviewee_id])


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=True)
    type = Column(SAEnum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(SAEnum(TransactionStatus), default=TransactionStatus.pending, nullable=False)
    payment_id = Column(String(255), nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="transactions")
    deal = relationship("Deal", back_populates="transactions")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    text = Column(Text, nullable=True)
    message_type = Column(String(20), default="text", nullable=False)
    file_id = Column(String(255), nullable=True)
    filename = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sender = relationship("User", back_populates="messages_sent", foreign_keys=[sender_id])
    receiver = relationship("User", back_populates="messages_received", foreign_keys=[receiver_id])


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    freelancer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    message = Column(Text, nullable=True)
    status = Column(SAEnum(InvitationStatus), default=InvitationStatus.pending, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    employer = relationship("User", back_populates="invitations_sent", foreign_keys=[employer_id])
    freelancer = relationship("User", back_populates="invitations_received", foreign_keys=[freelancer_id])
    job = relationship("Job", back_populates="invitations")


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(SAEnum(PromotionType), nullable=False)
    paid_amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    job = relationship("Job", back_populates="promotions")


class BotSettings(Base):
    __tablename__ = "bot_settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(500), nullable=False)


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(SAEnum(JobCategory), nullable=False)
    price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    orders_count = Column(Integer, default=0, nullable=False)
    is_promoted = Column(Boolean, default=False, nullable=False)
    promoted_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    seller = relationship("User", back_populates="services", foreign_keys=[seller_id])
    orders = relationship("ServiceOrder", back_populates="service")


class ServiceOrder(Base):
    __tablename__ = "service_orders"

    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    platform_fee = Column(Float, nullable=False)
    status = Column(String(20), default="escrow", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    service = relationship("Service", back_populates="orders")
    buyer = relationship("User", back_populates="service_orders_as_buyer", foreign_keys=[buyer_id])
    seller = relationship("User", back_populates="service_orders_as_seller", foreign_keys=[seller_id])


class PortfolioPhoto(Base):
    __tablename__ = "portfolio_photos"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_id = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="portfolio_photos")


class DisputeLog(Base):
    __tablename__ = "dispute_logs"

    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable=False)
    admin_telegram_id = Column(BigInteger, nullable=True)
    action = Column(String(100), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    deal = relationship("Deal", back_populates="dispute_logs")
