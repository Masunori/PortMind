"""Create editable agent prompt settings.

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_prompts",
        sa.Column("agent", sa.String(length=30), primary_key=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_prompts")
