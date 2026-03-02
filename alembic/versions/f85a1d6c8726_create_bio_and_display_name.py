"""Create bio and display name

Revision ID: f85a1d6c8726
Revises: f44bde9d40a8
Create Date: 2026-03-02 16:11:15.424463
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f85a1d6c8726"
down_revision: Union[str, Sequence[str], None] = "f44bde9d40a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("bio", sa.String(500), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(100), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "display_name")
    op.drop_column("users", "bio")