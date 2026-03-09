"""add comments table and comment count to posts"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "de6d262a97d1"
down_revision: Union[str, Sequence[str], None] = None
branch_labels = None
depends_on = None


def upgrade():

    op.create_table(
        "comments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("post_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
    )

    op.add_column(
        "posts",
        sa.Column("comment_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade():

    op.drop_column("posts", "comment_count")
    op.drop_table("comments")
