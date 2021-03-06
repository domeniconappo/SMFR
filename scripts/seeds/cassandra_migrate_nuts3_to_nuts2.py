from cassandra.auth import PlainTextAuthProvider
from cassandra.cluster import Cluster, default_lbp_factory

split_properties = [line.split("=") for line in open('.env')]
properties = {key: value.strip() for key, value in split_properties}
cassandra_user = properties.get('CASSANDRA_USER')
cassandra_password = properties.get('CASSANDRA_PASSWORD')

cluster = Cluster(auth_provider=PlainTextAuthProvider(username=cassandra_user, password=cassandra_password),
                  load_balancing_policy=default_lbp_factory())
session = cluster.connect('smfr_persistent')

rows = session.execute('SELECT collectionid, tweetid, nuts3, nuts3source, ttype FROM tweet')

for i, row in enumerate(rows, start=1):
    session.execute(
        'UPDATE tweet SET nuts2=%s, nuts2source=%s WHERE collectionid=%s AND tweetid=%s AND ttype=%s',
        (row.nuts3, row.nuts3source, row.collectionid, row.tweetid, row.ttype)
    )
    if not (i % 1000):
        print(i)
