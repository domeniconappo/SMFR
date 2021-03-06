import os
import sys
import tarfile
import glob
import json

from smfrcore.models.sql import Nuts2, Nuts3, create_app, sqldb
from sqlalchemy.orm import Session


def get_most_updated():
    export_dates = sorted([os.path.basename(p).split('_')[0]
                           for p in glob.glob(os.path.join(os.path.dirname(__file__),
                                                           'seeds/data/*_smfr_*.json.tar.gz'))
                           ], reverse=True
                          )
    return export_dates[0]


def objects_from_json(table):
    newer_date = get_most_updated()
    input_file = 'seeds/data/{}_smfr_{}.json.tar.gz'.format(newer_date, table)
    print('>>>>>>> Using', input_file)
    path = os.path.join(os.path.dirname(__file__), input_file)
    with tarfile.open(path, 'r:gz') as tar:
        archive = tar.getmembers()[0]
        init_f = tar.extractfile(archive)
        data = json.load(init_f)
        items = [Nuts2(**row) if table == 'nuts2' else Nuts3(**row) for row in data]
    return items


def update_nutstables():
    app = create_app()
    app.app_context().push()
    session = Session(bind=sqldb.engine)
    conn = sqldb.engine.connect()
    conn.execute('SET FOREIGN_KEY_CHECKS = 0;')
    print(' ---------- UPGRADING nuts2')
    print('Truncating in nuts2 table')
    conn.execute('TRUNCATE TABLE nuts2')
    print('Deleted all rows in nuts2 table')

    data_nuts2 = objects_from_json('nuts2')

    print('Bulk insert into Nuts2 table: %d rows' % len(data_nuts2))
    session.add_all(data_nuts2)
    session.flush()
    session.commit()

    print(' ---------- UPGRADING nuts3')
    print('Truncating in nuts3 table')
    conn.execute('TRUNCATE TABLE nuts3')
    print('Deleted all rows in nuts3 table')
    data_nuts3 = objects_from_json('nuts3')
    print('Bulk insert into Nuts3 table: %d rows' % len(data_nuts3))
    session.add_all(data_nuts3)
    session.flush()
    conn.execute('SET FOREIGN_KEY_CHECKS = 1;')
    session.commit()
    print('[OK] Updated nuts2 and nuts3 tables.')
    print('Check efas_id != 0....')
    nuts = Nuts2.query.all()
    nut0 = nuts[0]
    print('efas id', nut0.efas_id, 'efas name', nut0.efas_name)


if __name__ == '__main__':
    sys.exit(update_nutstables())
