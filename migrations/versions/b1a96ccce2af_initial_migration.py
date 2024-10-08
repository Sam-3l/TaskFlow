"""Initial migration

Revision ID: b1a96ccce2af
Revises: a890f101f32f
Create Date: 2024-08-31 00:57:44.277874

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1a96ccce2af'
down_revision = 'a890f101f32f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bio', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('date_joined', sa.Date(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('date_joined')
        batch_op.drop_column('bio')

    # ### end Alembic commands ###
