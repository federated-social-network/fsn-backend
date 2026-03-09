"""make post.user_id nullable to handle remote users

Revision ID: d4f5957ec1a6
Revises: e2b59acde090
Create Date: 2026-03-09 11:55:41.222413

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4f5957ec1a6'
down_revision: Union[str, Sequence[str], None] = 'e2b59acde090'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column(
        "posts",
        "user_id",
        existing_type=sa.String(),
        nullable=True
    )


def downgrade():
    op.alter_column(
        "posts",
        "user_id",
        existing_type=sa.String(),
        nullable=False
    )