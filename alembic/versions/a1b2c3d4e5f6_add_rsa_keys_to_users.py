"""add rsa keys to users

Revision ID: a1b2c3d4e5f6
Revises: 2f29db6648bc
Create Date: 2026-02-24 08:49:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "2f29db6648bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add RSA key pair columns to the users table for ActivityPub HTTP Signatures."""
    op.add_column(
        "users",
        sa.Column("rsa_private_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("rsa_public_key", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove RSA key pair columns from the users table."""
    op.drop_column("users", "rsa_public_key")
    op.drop_column("users", "rsa_private_key")
