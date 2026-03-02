"""add cascade to all foreign keys

Revision ID: 1d0be69de1df
Revises: f85a1d6c8726
Create Date: 2026-03-02
"""

from typing import Sequence, Union
from alembic import op


revision: str = "1d0be69de1df"
down_revision: Union[str, Sequence[str], None] = "f85a1d6c8726"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # POSTS → USERS
    op.drop_constraint("posts_user_id_fkey", "posts", type_="foreignkey")
    op.create_foreign_key(
        "posts_user_id_fkey",
        "posts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # CONNECTIONS → USERS (local_user_id)
    op.drop_constraint("connections_local_user_id_fkey", "connections", type_="foreignkey")
    op.create_foreign_key(
        "connections_local_user_id_fkey",
        "connections",
        "users",
        ["local_user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # CONNECTIONS → USERS (target_local_user_id)
    op.drop_constraint("connections_target_local_user_id_fkey", "connections", type_="foreignkey")
    op.create_foreign_key(
        "connections_target_local_user_id_fkey",
        "connections",
        "users",
        ["target_local_user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # PASSWORD_RESETS → USERS
    op.drop_constraint("password_resets_user_id_fkey", "password_resets", type_="foreignkey")
    op.create_foreign_key(
        "password_resets_user_id_fkey",
        "password_resets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("posts_user_id_fkey", "posts", type_="foreignkey")
    op.create_foreign_key(
        "posts_user_id_fkey",
        "posts",
        "users",
        ["user_id"],
        ["id"],
    )

    op.drop_constraint("connections_local_user_id_fkey", "connections", type_="foreignkey")
    op.create_foreign_key(
        "connections_local_user_id_fkey",
        "connections",
        "users",
        ["local_user_id"],
        ["id"],
    )

    op.drop_constraint("connections_target_local_user_id_fkey", "connections", type_="foreignkey")
    op.create_foreign_key(
        "connections_target_local_user_id_fkey",
        "connections",
        "users",
        ["target_local_user_id"],
        ["id"],
    )

    op.drop_constraint("password_resets_user_id_fkey", "password_resets", type_="foreignkey")
    op.create_foreign_key(
        "password_resets_user_id_fkey",
        "password_resets",
        "users",
        ["user_id"],
        ["id"],
    )