"""add incidents, product events, status slug, and email_sent

Revision ID: 20260617_01
Revises: 
Create Date: 2026-06-17
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260617_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("trigger_type", sa.String(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("checks_during_incident", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved_in_minutes", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_id", "incidents", ["id"])
    op.create_index("ix_incidents_site_id", "incidents", ["site_id"])
    op.create_index("ix_incidents_user_id", "incidents", ["user_id"])

    op.create_table(
        "product_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("event_props", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_events_id", "product_events", ["id"])
    op.create_index("ix_product_events_user_id", "product_events", ["user_id"])
    op.create_index("ix_product_events_event_name", "product_events", ["event_name"])

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("status_slug", sa.String(), nullable=True))
        batch_op.create_index("ix_users_status_slug", ["status_slug"], unique=True)

    with op.batch_alter_table("check_logs") as batch_op:
        batch_op.add_column(sa.Column("email_sent", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("check_logs") as batch_op:
        batch_op.drop_column("email_sent")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_status_slug")
        batch_op.drop_column("status_slug")

    op.drop_index("ix_product_events_event_name", table_name="product_events")
    op.drop_index("ix_product_events_user_id", table_name="product_events")
    op.drop_index("ix_product_events_id", table_name="product_events")
    op.drop_table("product_events")

    op.drop_index("ix_incidents_user_id", table_name="incidents")
    op.drop_index("ix_incidents_site_id", table_name="incidents")
    op.drop_index("ix_incidents_id", table_name="incidents")
    op.drop_table("incidents")
