"""Make pending_emails.job_id nullable

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('pending_emails', 'job_id', nullable=True)


def downgrade() -> None:
    op.alter_column('pending_emails', 'job_id', nullable=False)
