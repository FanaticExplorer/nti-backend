"""add application_status_history and mentorship_logs

Revision ID: f70eeebbaafa
Revises: a4bde0127997
Create Date: 2026-06-14 16:02:15.989498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f70eeebbaafa'
down_revision: Union[str, Sequence[str], None] = 'a4bde0127997'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "application_status_history",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("application_id", postgresql.UUID(), nullable=False),
        sa.Column("old_status", sa.String(50), nullable=False),
        sa.Column("new_status", sa.String(50), nullable=False),
        sa.Column("changed_by", postgresql.UUID(), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "mentorship_logs",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("mentorship_id", postgresql.UUID(), nullable=False),
        sa.Column("logged_by", postgresql.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("logged_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["mentorship_id"], ["mentorships.id"]),
        sa.ForeignKeyConstraint(["logged_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("mentorship_logs")
    op.drop_table("application_status_history")
