"""empty message

Revision ID: 9322c908cdee
Revises: ba194f1bbc32
Create Date: 2018-08-27 16:50:51.664570

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
from sqlalchemy.dialects.mysql import LONGTEXT


# revision identifiers, used by Alembic.
revision = '9322c908cdee'
down_revision = 'ba194f1bbc32'
branch_labels = None
depends_on = None


class LongJSONType(sqlalchemy_utils.types.json.JSONType):
    impl = LONGTEXT


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('aggregation', sa.Column('relevant_tweets', LongJSONType(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('aggregation', 'relevant_tweets')
    # ### end Alembic commands ###
