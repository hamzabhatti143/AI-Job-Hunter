"""add user profile and smtp fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-04 00:01:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("username", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("smtp_host", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("smtp_port", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("smtp_user", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("smtp_password", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_index("ix_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "smtp_password")
    op.drop_column("users", "smtp_port")
    op.drop_column("users", "smtp_host")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
    op.drop_column("users", "name")
