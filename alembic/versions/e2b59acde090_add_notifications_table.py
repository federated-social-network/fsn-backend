"""add notifications table

Revision ID: e2b59acde090
Revises: 0d9c4af0d2e6
Create Date: 2026-03-06 11:24:38.414006
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "e2b59acde090"
down_revision: Union[str, Sequence[str], None] = "0d9c4af0d2e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("is_read", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_index("idx_notification_recipient", "notifications", ["recipient_id"])

    op.create_index(
        "idx_notification_unread", "notifications", ["recipient_id", "is_read"]
    )


def downgrade() -> None:
    op.drop_index("idx_notification_unread", table_name="notifications")
    op.drop_index("idx_notification_recipient", table_name="notifications")
    op.drop_table("notifications")
