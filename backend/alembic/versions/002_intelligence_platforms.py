"""Add platforms column to intelligence_records

Revision ID: 002
Revises: 001
Create Date: 2026-09-26 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "intelligence_records",
        sa.Column("platforms", postgresql.JSON(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("intelligence_records", "platforms")
