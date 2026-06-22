"""rename_og_image_url_to_og_image

Revision ID: e3f4a5b6c7d8
Revises: c1d2e3f4a5b6
Create Date: 2026-06-22 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE content_pages RENAME COLUMN og_image_url TO og_image")


def downgrade() -> None:
    op.execute("ALTER TABLE content_pages RENAME COLUMN og_image TO og_image_url")
