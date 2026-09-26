"""Initial schema - create all tables

Revision ID: 001
Revises:
Create Date: 2026-09-14 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums
    op.create_table(
        "personas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("persona_config", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "platform", sa.Enum("TELEGRAM", "FACEBOOK", "ZALO", name="platform"), nullable=False
        ),
        sa.Column("username", sa.String(length=200), nullable=False),
        sa.Column("credentials", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("persona_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "health",
            sa.Enum("GREEN", "YELLOW", "RED", "BLACK", name="accounthealth"),
            nullable=False,
        ),
        sa.Column("proxy_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["persona_id"],
            ["personas.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column(
            "platform", sa.Enum("TELEGRAM", "FACEBOOK", "ZALO", name="platform"), nullable=False
        ),
        sa.Column(
            "category",
            sa.Enum(
                "PRIVATE_INVESTIGATOR",
                "CURRENCY_EXCHANGER",
                "FREELANCER",
                "DATA_SELLER",
                name="intelligencecategory",
            ),
            nullable=False,
        ),
        sa.Column("keywords", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("target_region", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "RUNNING", "PAUSED", "COMPLETED", "FAILED", name="taskstatus"),
            nullable=False,
        ),
        sa.Column("config", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_user_id", sa.String(length=200), nullable=False),
        sa.Column("target_display_name", sa.String(length=300), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "IDLE",
                "GREETING",
                "PROBING",
                "EXTRACTION",
                "PIVOT",
                "EXIT",
                "COOLDOWN",
                name="conversationstate",
            ),
            nullable=False,
        ),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "direction", sa.Enum("INBOUND", "OUTBOUND", name="messagedirection"), nullable=False
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("metadata", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "intelligence_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "platform", sa.Enum("TELEGRAM", "FACEBOOK", "ZALO", name="platform"), nullable=False
        ),
        sa.Column("target_user_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=True),
        sa.Column("profile_url", sa.String(length=1000), nullable=True),
        sa.Column("avatar_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "PRIVATE_INVESTIGATOR",
                "CURRENCY_EXCHANGER",
                "FREELANCER",
                "DATA_SELLER",
                name="intelligencecategory",
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("signals", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("extracted_contacts", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("business_info", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "activity_status",
            sa.Enum("ACTIVE", "DORMANT", "INACTIVE", name="activitystatus"),
            nullable=False,
        ),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_rate", sa.Float(), nullable=True),
        sa.Column(
            "review_status",
            sa.Enum("PENDING", "REVIEWED", "APPROVED", "REJECTED", name="reviewstatus"),
            nullable=False,
        ),
        sa.Column("operator_notes", sa.Text(), nullable=True),
        sa.Column("dedup_fingerprint", sa.String(length=128), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_intelligence_records_dedup_fingerprint"),
        "intelligence_records",
        ["dedup_fingerprint"],
        unique=False,
    )

    op.create_table(
        "script_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "PRIVATE_INVESTIGATOR",
                "CURRENCY_EXCHANGER",
                "FREELANCER",
                "DATA_SELLER",
                name="intelligencecategory",
            ),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("templates", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=200), nullable=True),
        sa.Column("details", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("operator_id", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("script_templates")
    op.drop_index(
        op.f("ix_intelligence_records_dedup_fingerprint"), table_name="intelligence_records"
    )
    op.drop_table("intelligence_records")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("tasks")
    op.drop_table("accounts")
    op.drop_table("personas")

    # Drop enums
    op.execute("DROP TYPE platform")
    op.execute("DROP TYPE taskstatus")
    op.execute("DROP TYPE accounthealth")
    op.execute("DROP TYPE conversationstate")
    op.execute("DROP TYPE intelligencecategory")
    op.execute("DROP TYPE activitystatus")
    op.execute("DROP TYPE reviewstatus")
    op.execute("DROP TYPE messagedirection")
