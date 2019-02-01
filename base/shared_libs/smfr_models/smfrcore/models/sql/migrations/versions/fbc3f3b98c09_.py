"""empty message

Revision ID: fbc3f3b98c09
Revises: 
Create Date: 2018-08-03 14:24:35.927690

"""

import os
import tarfile

import ujson as json
import sqlalchemy_utils
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

from smfrcore.models.sql import Nuts2, Nuts3, TwitterCollection, User

# revision identifiers, used by Alembic.
revision = 'fbc3f3b98c09'
down_revision = None
branch_labels = None
depends_on = None


class LongJSONType(sqlalchemy_utils.types.json.JSONType):
    impl = LONGTEXT


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('collector_configuration',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('name', sa.String(length=500), nullable=True),
                    sa.Column('consumer_key', sa.String(length=200), nullable=False),
                    sa.Column('consumer_secret', sa.String(length=200), nullable=False),
                    sa.Column('access_token', sa.String(length=200), nullable=False),
                    sa.Column('access_token_secret', sa.String(length=200), nullable=False),
                    sa.PrimaryKeyConstraint('id'),
                    mysql_charset='utf8mb4',
                    mysql_collate='utf8mb4_general_ci',
                    mysql_engine='InnoDB'
                    )

    op.create_table('nuts2',
                    sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
                    sa.Column('efas_id', sa.Integer(), nullable=False),
                    sa.Column('efas_name', sa.String(length=1000), nullable=True),
                    sa.Column('nuts_id', sa.String(length=10), nullable=True),
                    sa.Column('country', sa.String(length=500), nullable=True),
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
    op.create_index('bbox_index', 'nuts2', ['min_lon', 'min_lat', 'max_lon', 'max_lat'], unique=False)
    op.create_index(op.f('ix_nuts2_efas_id'), 'nuts2', ['efas_id'], unique=False)

    op.create_table('nuts3',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('efas_id', sa.Integer(), nullable=False),
                    sa.Column('name', sa.String(length=500), nullable=False),
                    sa.Column('name_ascii', sa.String(length=500), nullable=False),
                    sa.Column('latitude', sa.Float(), nullable=False),
                    sa.Column('longitude', sa.Float(), nullable=False),
                    sa.Column('names', sqlalchemy_utils.types.json.JSONType(), nullable=False),
                    sa.Column('properties', sqlalchemy_utils.types.json.JSONType(), nullable=False),
                    sa.Column('country_name', sa.String(length=500), nullable=False),
                    sa.Column('nuts_id', sa.String(length=10), nullable=True),
                    sa.Column('country_code', sa.String(length=5), nullable=False),
                    sa.PrimaryKeyConstraint('id'),
                    mysql_charset='utf8mb4',
                    mysql_collate='utf8mb4_general_ci',
                    mysql_engine='InnoDB'
                    )
    op.create_index(op.f('ix_nuts3_efas_id'), 'nuts3', ['efas_id'], unique=False)
    op.create_index(op.f('ix_nuts3_name_ascii'), 'nuts3', ['name_ascii'], unique=False)

    op.create_table('users',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('name', sa.String(length=200), nullable=True),
                    sa.Column('email', sa.String(length=100), nullable=True),
                    sa.Column('password_hash', sa.String(length=128), nullable=True),
                    sa.Column('role', sqlalchemy_utils.types.choice.ChoiceType(User.ROLES), nullable=False),
                    sa.PrimaryKeyConstraint('id'),
                    mysql_charset='utf8mb4',
                    mysql_collate='utf8mb4_general_ci',
                    mysql_engine='InnoDB'
                    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table('virtual_twitter_collection',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('forecast_id', sa.Integer(), nullable=True),
                    sa.Column('trigger', sqlalchemy_utils.types.choice.ChoiceType(TwitterCollection.TRIGGERS), nullable=False),
                    sa.Column('tracking_keywords', sqlalchemy_utils.types.scalar_list.ScalarListType(), nullable=True),
                    sa.Column('locations', sqlalchemy_utils.types.json.JSONType(), nullable=True),
                    sa.Column('languages', sqlalchemy_utils.types.scalar_list.ScalarListType(), nullable=True),
                    sa.Column('status', sqlalchemy_utils.types.choice.ChoiceType(TwitterCollection.STATUSES), nullable=False),
                    sa.Column('nuts2', sa.String(length=50), nullable=True),
                    sa.Column('started_at', sa.TIMESTAMP(), nullable=True),
                    sa.Column('stopped_at', sa.TIMESTAMP(), nullable=True),
                    sa.Column('runtime', sa.TIMESTAMP(), nullable=True),
                    sa.Column('user_id', sa.Integer(), nullable=True),
                    sa.Column('configuration_id', sa.Integer(), nullable=True),
                    sa.ForeignKeyConstraint(['configuration_id'], ['collector_configuration.id'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id'),
                    mysql_charset='utf8mb4',
                    mysql_collate='utf8mb4_general_ci',
                    mysql_engine='InnoDB'
                    )

    op.create_table('aggregation',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('collection_id', sa.Integer(), nullable=True),
                    sa.Column('values', LongJSONType(), nullable=False),
                    sa.Column('last_tweetid_collected', sa.BigInteger(), nullable=True),
                    sa.Column('last_tweetid_annotated', sa.BigInteger(), nullable=True),
                    sa.Column('last_tweetid_geotagged', sa.BigInteger(), nullable=True),
                    sa.Column('timestamp_start', sa.TIMESTAMP(), nullable=True),
                    sa.Column('timestamp_end', sa.TIMESTAMP(), nullable=True),
                    sa.ForeignKeyConstraint(['collection_id'], ['virtual_twitter_collection.id'], ),
                    sa.PrimaryKeyConstraint('id'),
                    mysql_charset='utf8mb4',
                    mysql_collate='utf8mb4_general_ci',
                    mysql_engine='InnoDB'
                    )
    # ### end Alembic commands ###

    path = os.path.join(os.path.dirname(__file__), '../../data/smfr_nuts2.json.tar.gz')
    nuts2_table = Nuts2.__table__
    with tarfile.open(path, 'r:gz') as tar:
        archive = tar.getmembers()[0]
        init_f = tar.extractfile(archive)
        init_data = json.load(init_f, precise_float=True)
        op.bulk_insert(nuts2_table, init_data)

    path = os.path.join(os.path.dirname(__file__), '../../data/smfr_nuts3.json.tar.gz')
    nuts3_table = Nuts3.__table__
    with tarfile.open(path, 'r:gz') as tar:
        archive = tar.getmembers()[0]
        init_f = tar.extractfile(archive)
        init_data = json.load(init_f, precise_float=True)
        for e in init_data:
            del e['id']
        op.bulk_insert(nuts3_table, init_data)


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('aggregation')
    op.drop_table('virtual_twitter_collection')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_nuts3_name_ascii'), table_name='nuts3')
    op.drop_index(op.f('ix_nuts3_efas_id'), table_name='nuts3')
    op.drop_table('nuts3')
    op.drop_index(op.f('ix_nuts2_efas_id'), table_name='nuts2')
    op.drop_index('bbox_index', table_name='nuts2')
    op.drop_table('nuts2')
    op.drop_table('collector_configuration')
    # ### end Alembic commands ###
