"""empty message

Revision ID: e9b27708284b
Revises: f99ee53dfd20
Create Date: 2018-06-28 11:44:05.169322

"""
import os

import ujson as json
import sqlalchemy_utils
from alembic import op
import sqlalchemy as sa

from smfrcore.models.sqlmodels import Nuts3

# revision identifiers, used by Alembic.
revision = 'e9b27708284b'
down_revision = 'f99ee53dfd20'
branch_labels = None
depends_on = None


class LongJSONType(sqlalchemy_utils.types.json.JSONType):
    impl = sa.dialects.mysql.types.LONGTEXT


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    nuts2_table = op.create_table('nuts2',
                                  sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
                                  sa.Column('efas_id', sa.Integer(), nullable=False),
                                  sa.Column('efas_name', sa.String(length=1000), nullable=True),
                                  sa.Column('nuts_id', sa.String(length=10), nullable=True),
                                  sa.Column('country', sa.String(length=500), nullable=True),
                                  sa.Column('mean_pl', sa.Float(), nullable=True),
                                  sa.Column('geometry', LongJSONType(), nullable=False),
                                  sa.Column('country_code', sa.String(length=5), nullable=True),
                                  sa.Column('min_lon', sa.Float(), nullable=True),
                                  sa.Column('max_lon', sa.Float(), nullable=True),
                                  sa.Column('min_lat', sa.Float(), nullable=True),
                                  sa.Column('max_lat', sa.Float(), nullable=True),
                                  sa.PrimaryKeyConstraint('id'),
                                  mysql_charset='utf8mb4',
                                  mysql_collate='utf8mb4_general_ci',
                                  mysql_engine='InnoDB'
                                  )
    op.create_index(op.f('ix_nuts2_efas_id'), 'nuts2', ['efas_id'], unique=False)
    path = os.path.join(os.path.dirname(__file__), './nuts2wgs84.json')
    with open(path) as init_f:
        init_data = json.load(init_f, precise_float=True)
        op.bulk_insert(nuts2_table, init_data)

    op.add_column('nuts3', sa.Column('join_id', sa.Integer(), nullable=False))
    op.create_index(op.f('ix_nuts3_join_id'), 'nuts3', ['join_id'], unique=False)
    # ### end Alembic commands ###
    path = os.path.join(os.path.dirname(__file__), './nuts3.json')
    nuts3_table = Nuts3.__table__
    with open(path) as init_f:
        init_data = json.load(init_f, precise_float=True)
        for e in init_data:
            del e['id']
        op.bulk_insert(nuts3_table, init_data)


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_nuts3_join_id'), table_name='nuts3')
    op.drop_column('nuts3', 'join_id')
    op.drop_index(op.f('ix_nuts2_efas_id'), table_name='nuts2')
    op.drop_table('nuts2')
    # ### end Alembic commands ###
