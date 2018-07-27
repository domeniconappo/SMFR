"""empty message

Revision ID: 03e961ff91b8
Revises: 80ba1ee8df05
Create Date: 2018-07-25 14:35:05.324863

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '03e961ff91b8'
down_revision = '80ba1ee8df05'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_nuts3_join_id', table_name='nuts3')
    op.drop_column('nuts3', 'join_id')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('nuts3', sa.Column('join_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False))
    op.create_index('ix_nuts3_join_id', 'nuts3', ['join_id'], unique=False)
    # ### end Alembic commands ###