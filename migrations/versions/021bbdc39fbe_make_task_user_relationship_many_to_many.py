"""Make Task-User relationship many-to-many

Revision ID: 021bbdc39fbe
Revises: b4ab815e054b
Create Date: 2025-04-04 13:49:17.074735

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy import Integer

# revision identifiers, used by Alembic.
revision = '021bbdc39fbe'
down_revision = 'b4ab815e054b'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create the new M2M table
    op.create_table('task_user_association',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['task.id']),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('user_id', 'task_id')
    )

    # 2. Migrate existing data from task.assigned_to_user_id to task_user_association
    # Define a temporary table to select from
    task = table('task',
        column('id', Integer),
        column('assigned_to_user_id', Integer)
    )

    conn = op.get_bind()
    results = conn.execute(sa.select(task.c.id, task.c.assigned_to_user_id)).fetchall()

    for task_id, user_id in results:
        if user_id is not None:
            conn.execute(
                sa.text("INSERT INTO task_user_association (user_id, task_id) VALUES (:user_id, :task_id)"),
                {"user_id": user_id, "task_id": task_id}
            )

    # 3. Drop the old foreign key and column
    with op.batch_alter_table('task', schema=None) as batch_op:
        batch_op.drop_constraint('task_assigned_to_user_id_fkey', type_='foreignkey')
        batch_op.drop_column('assigned_to_user_id')


def downgrade():
    with op.batch_alter_table('task', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assigned_to_user_id', sa.INTEGER(), autoincrement=False, nullable=True))
        batch_op.create_foreign_key('task_assigned_to_user_id_fkey', 'user', ['assigned_to_user_id'], ['id'])

    op.drop_table('task_user_association')
