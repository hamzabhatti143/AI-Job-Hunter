"""Make sent_emails.job_id nullable

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-20
"""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('sent_emails', 'job_id', nullable=True)


def downgrade() -> None:
    op.alter_column('sent_emails', 'job_id', nullable=False)
