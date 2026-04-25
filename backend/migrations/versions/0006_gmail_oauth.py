"""Add Gmail OAuth fields to users and gmail_thread_id to sent_emails

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('gmail_access_token', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('gmail_refresh_token', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('gmail_token_expiry', sa.DateTime(timezone=True), nullable=True))
    op.add_column('sent_emails', sa.Column('gmail_thread_id', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('sent_emails', 'gmail_thread_id')
    op.drop_column('users', 'gmail_token_expiry')
    op.drop_column('users', 'gmail_refresh_token')
    op.drop_column('users', 'gmail_access_token')
