"""initial schema - all tables

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-11 09:50:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("email", sa.String(), unique=True, nullable=True),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("public_key", sa.Text(), nullable=True),
        sa.Column("private_key", sa.Text(), nullable=True),
        sa.Column("bio", sa.String(500), nullable=True),
        sa.Column("display_name", sa.String(100), nullable=True),
    )

    # --- posts ---
    op.create_table(
        "posts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author", sa.String(), nullable=False),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("origin_instance", sa.String(), nullable=False),
        sa.Column("is_remote", sa.Boolean(), default=False),
        sa.Column("like_count", sa.Integer(), default=0),
        sa.Column("visibility", sa.String(), nullable=False, server_default="public"),
        sa.Column("comment_count", sa.Integer(), default=0),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # --- activities ---
    op.create_table(
        "activities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("object", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("is_local", sa.Boolean(), default=True),
        sa.Column("is_delivered", sa.Boolean(), default=False),
    )

    # --- connections ---
    op.create_table(
        "connections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "local_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_local_user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("remote_actor_url", sa.String(), nullable=True),
        sa.Column("remote_inbox_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # --- password_resets ---
    op.create_table(
        "password_resets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("otp", sa.String(), nullable=False),
        sa.Column("otp_expires_at", sa.DateTime(), nullable=False),
        sa.Column("is_used", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # --- likes ---
    op.create_table(
        "likes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "post_id",
            sa.String(),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "post_id", name="unique_user_post_like"),
    )

    # --- comments ---
    op.create_table(
        "comments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "post_id",
            sa.String(),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "post_id", "content", name="unique_comment"),
    )

    # --- messages ---
    op.create_table(
        "messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "sender_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "receiver_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_chat_pair", "messages", ["sender_id", "receiver_id"])

    # --- notifications ---
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "recipient_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("object_id", sa.String(), nullable=True),
        sa.Column("is_read", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_notification_recipient", "notifications", ["recipient_id"])


def downgrade() -> None:
    op.drop_index("idx_notification_recipient", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("idx_chat_pair", table_name="messages")
    op.drop_table("messages")
    op.drop_table("comments")
    op.drop_table("likes")
    op.drop_table("password_resets")
    op.drop_table("connections")
    op.drop_table("activities")
    op.drop_table("posts")
    op.drop_table("users")
