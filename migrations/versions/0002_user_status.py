"""users: is_active and token_version (disable accounts, end sessions after a password change)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13 14:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default fills the columns for users that already exist
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("token_version")
        batch_op.drop_column("is_active")
