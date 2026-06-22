"""add_tech_specs

Revision ID: c1d2e3f4a5b6
Revises: bf6f8efa9642
Create Date: 2026-06-22 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'bf6f8efa9642'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE tech_spec_status AS ENUM (
                'draft', 'published', 'in_pairing', 'assigned',
                'in_realization', 'closed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    op.execute("""
        CREATE TABLE tech_specs (
            id UUID NOT NULL,
            organization_id UUID NOT NULL,
            call_id UUID NOT NULL,
            product_owner_id UUID,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            budget VARCHAR(255),
            status tech_spec_status NOT NULL DEFAULT 'draft',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            PRIMARY KEY (id),
            FOREIGN KEY (organization_id) REFERENCES organizations (id),
            FOREIGN KEY (call_id) REFERENCES calls (id),
            FOREIGN KEY (product_owner_id) REFERENCES users (id)
        )
    """)

    op.execute("""
        ALTER TABLE applications
        ADD COLUMN tech_spec_id UUID
        REFERENCES tech_specs (id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE applications DROP COLUMN IF EXISTS tech_spec_id")
    op.execute("DROP TABLE IF EXISTS tech_specs")
    op.execute("DROP TYPE IF EXISTS tech_spec_status")
