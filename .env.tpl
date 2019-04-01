# BASIC CONFIGURATION
LOGGING_LEVEL=ERROR
DEVELOPMENT=0
DOCKER_HOST_IP=10.0.2.15
# DOCKER REGISTRY CONFIGURATION
DOCKER_REGISTRY=index.docker.io
DOCKER_ID_USER=user
DOCKER_ID_PASSWORD=pass

# DOCKER IMAGES CONFIGURATION
KAFKA_IMAGE=wurstmeister/kafka:latest
ZOOKEEPER_IMAGE=wurstmeister/zookeeper

PYTHON_BASE_IMAGE=python:3.6
CASSANDRA_BASE_IMAGE=cassandra:3.11.2
MYSQL_BASE_IMAGE=mysql:8.0.11
GEONAMES_BASE_IMAGE=docker.elastic.co/elasticsearch/elasticsearch:5.5.3
WEB_BASE_IMAGE=python:3.5-stretch
ALPINE_IMAGE=itsupport/alpine

SMFR_IMAGE=efas/smfr_base
BACKUPPER_IMAGE=efas/backupper
GEONAMES_IMAGE=efas/geonames
CASSANDRA_IMAGE=efas/cassandrasmfr
MYSQL_IMAGE=efas/mysql
PERSISTER_IMAGE=efas/persister
ANNOTATOR_IMAGE=efas/annotator
GEOCODER_IMAGE=efas/geocoder
AGGREGATOR_IMAGE=efas/aggregator
PRODUCTS_IMAGE=efas/products
COLLECTORS_IMAGE=efas/collectors
RESTSERVER_IMAGE=efas/restserver
WEB_IMAGE=efas/web
TEST_IMAGE=efas/integration_tests

# MYSQL CONFIGURATION
MYSQL_USER=user
MYSQL_PASSWORD=pass
MYSQL_DBNAME=smfr
MYSQL_HOST=mysql

# CASSANDRA CONFIGURATION
CASSANDRA_KEYSPACE=smfr_persistent
CASSANDRA_HOST=cassandrasmfr
CASSANDRA_NODES=cassandrasmfr,cassandra-node-1,cassandra-node-2
CASSANDRA_USE_CLUSTER=0
CASSANDRA_PORT=9042
CASSANDRA_USER=user
CASSANDRA_PASSWORD=pass
CASSANDRA_FETCH_SIZE=1000

# BACKUP config
BACKUP_FOLDER=/H07_Global1/smfr/backups

# KAFKA CONFIGURATION
KAFKA_BOOTSTRAP_SERVERS=kafka1:9092,kafka2:9092
PERSISTER_KAFKA_TOPIC=persister
ANNOTATOR_KAFKA_TOPIC=annotator
GEOCODER_KAFKA_TOPIC=geocoder
ALL_ANNOTATOR_KAFKA_TOPICS=annotator-en:1:1,annotator-es:1:1,annotator-fr:1:1,annotator-it:1:1,annotator-de:1:1,annotator-ro:1:1

# REST SERVICES PORTS CONFIGURATIONS
RESTSERVER_PORT=5555
ANNOTATOR_PORT=5556
GEOCODER_PORT=5557
PERSISTER_PORT=5558
COLLECTORS_PORT=5559
ANNOTATOR_HOST=annotator
GEOCODER_HOST=geocoder
RESTSERVER_HOST=restserver
PERSISTER_HOST=persister
COLLECTORS_HOST=collectors

# REST API CONFIGURATION
NUM_SAMPLES=100
FLOOD_KEYWORDS_PATH=./collectors/src/config/flood_keywords.yaml

# TWITTER STREAMER API SECRETS (Background, OnDemand and Manual collectors)
START_COLLECTORS=yes
TWITTERBG_CONSUMER_KEY=XXXxxxYYYyyyZZZzzz
TWITTERBG_CONSUMER_SECRET=XXXxxxYYYyyyZZZzzz
TWITTERBG_ACCESS_TOKEN=XXXxxxYYYyyyZZZzzz
TWITTERBG_ACCESS_TOKEN_SECRET=XXXxxxYYYyyyZZZzzz
TWITTEROD_CONSUMER_KEY=XXXxxxYYYyyyZZZzzz
TWITTEROD_CONSUMER_SECRET=XXXxxxYYYyyyZZZzzz
TWITTEROD_ACCESS_TOKEN=XXXxxxYYYyyyZZZzzz
TWITTEROD_ACCESS_TOKEN_SECRET=XXXxxxYYYyyyZZZzzz
TWITTERMA_CONSUMER_KEY=XXXxxxYYYyyyZZZzzz
TWITTERMA_CONSUMER_SECRET=XXXxxxYYYyyyZZZzzz
TWITTERMA_ACCESS_TOKEN=XXXxxxYYYyyyZZZzzz
TWITTERMA_ACCESS_TOKEN_SECRET=XXXxxxYYYyyyZZZzzz

# ANNOTATOR COMPONENT CONFIGURATION
GIT_REPO_MODELS=https://user:pass@bitbucket.org/lorinivalerio/smfr_models_data.git

# RRA CONFIGURATION
FTP_HOST=123.213.021.101
FTP_USER=user
FTP_PASS=pass
FTP_PATH=/remote/folder/
DOWNLOAD_FOLDER=/downloaded
RRA_ONDEMAND_FILENAME=filename{}.csv
RRA_FETCH_SCHEDULING=00,03,06,09,12,15,18,21
CHECK_ONDEMAND_RUNTIME_SCHEDULING=00,06,12,18
CHECK_JOBS_INTERVAL_SECONDS=21600

# AGGREGATOR COMPONENT CONFIGURATION
AGGREGATOR_RUN_CONF=--running
AGGREGATOR_SCHEDULING_MINUTES=30
NUM_RELEVANT_TWEETS_AGGREGATED=100
MIN_RELEVANT_FLOOD_PROBABILITY=90
FLOOD_PROBABILITY_RANGES=0-10,10-90,90-100

# PRODUCTS COMPONENT CONFIGURATION
THRESHOLDS=10:5:9
NUM_RELEVANT_TWEETS_PRODUCTS=5
PRODUCTS_OUTPUT=./products/output
HERE_APP_ID=XXXXXXXXXXXXXXXXXXXX
HERE_APP_CODE=YYYYYYYYYYYYYYYYYY
KAJO_FTP_SERVER=207.180.226.197
KAJO_FTP_USER=jrc
KAJO_FTP_PASSWORD=XXXXXXXXX
KAJO_FTP_FOLDER=/home/jrc
RAMNODE_FTP_SERVER=81.4.107.12
RAMNODE_FTP_USER=smfr
RAMNODE_FTP_PASSWORD=XXXXXXXXX
RAMNODE_FTP_FOLDER=/home/smfr
# INCLUDE_PAST_COLLECTIONS=<collection_id>
DOWNLOAD_RRA_SINCE=latest
