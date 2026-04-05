"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-04 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("api_key_hash", sa.Text(), nullable=False),
        sa.Column("resume_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "job_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=False),
        sa.Column("match_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("job_url", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="matched", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_job_matches_user_id", "job_matches", ["user_id"])
    op.create_index("ix_job_matches_status", "job_matches", ["status"])
    op.create_index("ix_job_matches_created_at", "job_matches", ["created_at"])

    op.create_table(
        "extracted_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("job_matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("is_valid", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_extracted_emails_user_id", "extracted_emails", ["user_id"])
    op.create_index("ix_extracted_emails_job_id", "extracted_emails", ["job_id"])

    op.create_table(
        "pending_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("job_matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("draft_content", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pending_emails_user_id", "pending_emails", ["user_id"])
    op.create_index("ix_pending_emails_status", "pending_emails", ["status"])

    op.create_table(
        "sent_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("job_matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pending_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pending_emails.id"), nullable=False),
        sa.Column("recipient_email", sa.Text(), nullable=False),
        sa.Column("email_content", sa.Text(), nullable=False),
        sa.Column("resume_attached", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_sent_emails_user_id", "sent_emails", ["user_id"])

    op.create_table(
        "activity_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("event_detail", postgresql.JSONB(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_activity_log_user_id", "activity_log", ["user_id"])
    op.create_index("ix_activity_log_event_type", "activity_log", ["event_type"])
    op.create_index("ix_activity_log_logged_at", "activity_log", ["logged_at"])


def downgrade() -> None:
    op.drop_table("activity_log")
    op.drop_table("sent_emails")
    op.drop_table("pending_emails")
    op.drop_table("extracted_emails")
    op.drop_table("job_matches")
    op.drop_table("users")
