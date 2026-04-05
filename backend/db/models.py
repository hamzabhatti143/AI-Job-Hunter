import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, Numeric, ForeignKey, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True, index=True)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    resume_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mail credentials (stored for reuse in pipeline)
    smtp_host: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_user: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job_matches: Mapped[list["JobMatch"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    extracted_emails: Mapped[list["ExtractedEmail"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    pending_emails: Mapped[list["PendingEmail"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sent_emails: Mapped[list["SentEmail"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    activity_logs: Mapped[list["ActivityLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class JobMatch(Base):
    __tablename__ = "job_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    match_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    job_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="matched", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="job_matches")
    extracted_emails: Mapped[list["ExtractedEmail"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    pending_emails: Mapped[list["PendingEmail"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    sent_emails: Mapped[list["SentEmail"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class ExtractedEmail(Base):
    __tablename__ = "extracted_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_matches.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="extracted_emails")
    job: Mapped["JobMatch"] = relationship(back_populates="extracted_emails")


class PendingEmail(Base):
    __tablename__ = "pending_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("job_matches.id", ondelete="CASCADE"), index=True, nullable=True)
    draft_content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="pending_emails")
    job: Mapped["JobMatch"] = relationship(back_populates="pending_emails")
    sent_email: Mapped["SentEmail | None"] = relationship(back_populates="pending", cascade="all, delete-orphan")


class SentEmail(Base):
    __tablename__ = "sent_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("job_matches.id", ondelete="CASCADE"), index=True)
    pending_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pending_emails.id"), index=True)
    recipient_email: Mapped[str] = mapped_column(Text, nullable=False)
    email_content: Mapped[str] = mapped_column(Text, nullable=False)
    resume_attached: Mapped[bool] = mapped_column(Boolean, default=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="sent_emails")
    job: Mapped["JobMatch"] = relationship(back_populates="sent_emails")
    pending: Mapped["PendingEmail"] = relationship(back_populates="sent_email")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    event_detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    user: Mapped["User"] = relationship(back_populates="activity_logs")
