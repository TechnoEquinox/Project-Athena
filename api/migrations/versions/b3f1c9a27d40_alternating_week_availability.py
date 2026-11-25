"""Alternating-week availability

Revision ID: b3f1c9a27d40
Revises: 858a1c1807bb
Create Date: 2026-11-24 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f1c9a27d40'
down_revision = '858a1c1807bb'
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows get cycle_weeks = 1 and week = 0, so they behave exactly as before.
    with op.batch_alter_table('tech_availability', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cycle_weeks', sa.SmallInteger(), server_default=sa.text('1'), nullable=False))
        batch_op.add_column(sa.Column('cycle_start', sa.Date(), nullable=True))
        batch_op.create_check_constraint(batch_op.f('ck_tech_availability_cycle_weeks_range'), 'cycle_weeks BETWEEN 1 AND 2')

    with op.batch_alter_table('availability_window', schema=None) as batch_op:
        batch_op.add_column(sa.Column('week', sa.SmallInteger(), server_default=sa.text('0'), nullable=False))
        batch_op.create_check_constraint(batch_op.f('ck_availability_window_week_range'), 'week BETWEEN 0 AND 1')


def downgrade():
    with op.batch_alter_table('availability_window', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('ck_availability_window_week_range'), type_='check')
        batch_op.drop_column('week')

    with op.batch_alter_table('tech_availability', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('ck_tech_availability_cycle_weeks_range'), type_='check')
        batch_op.drop_column('cycle_start')
        batch_op.drop_column('cycle_weeks')