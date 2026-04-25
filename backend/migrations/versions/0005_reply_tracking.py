"""Add reply tracking columns to sent_emails

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sent_emails', sa.Column('replied_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sent_emails', sa.Column('reply_content', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('sent_emails', 'reply_content')
    op.drop_column('sent_emails', 'replied_at')
