# BASIC CONFIGURATION
LOGGING_LEVEL=ERROR
DEVELOPMENT=0

# DATA FOLDER CONFIGURATION
SMFR_DATADIR=/DATA/smfr/data

# MYSQL CONFIGURATION
MYSQL_USER=user
MYSQL_PASSWORD=pass
MYSQL_DBNAME=smfr

# CASSANDRA CONFIGURATION
CASSANDRA_KEYSPACE=smfr_persistent
CASSANDRA_HOST=cassandrasmfr
CASSANDRA_NODES=cassandrasmfr,cassandra-node-1,cassandra-node-2
CASSANDRA_USE_CLUSTER=0
CASSANDRA_PORT=9042
CASSANDRA_USER=user
CASSANDRA_PASSWORD=pass
CASSANDRA_FETCH_SIZE=1000

# KAFKA CONFIGURATION
KAFKA_BOOTSTRAP_SERVER=kafka:9094
PERSISTER_KAFKA_TOPIC=persister
ANNOTATOR_KAFKA_TOPIC=annotator
GEOCODER_KAFKA_TOPIC=geocoder

# REST SERVICES PORTS CONFIGURATIONS
RESTSERVER_PORT=5555
ANNOTATOR_PORT=5556
GEOCODER_PORT=5557

# REST API CONFIGURATION
NUM_SAMPLES=100

# ANNOTATOR COMPONENT CONFIGURATION
GIT_REPO_MODELS=https://user:pass@bitbucket.org/lorinivalerio/smfr_models_data.git

# RRA CONFIGURATION

FTP_HOST=123.213.021.101
FTP_USER=user
FTP_PASS=pass
FTP_PATH=/remote/folder/
DOWNLOAD_FOLDER=/downloaded
RRA_ONDEMAND_FILENAME=filename{}.csv

# AGGREGATOR COMPONENT CONFIGURATION
AGGREGATOR_RUN_CONF=--running
AGGREGATOR_SCHEDULING_MINUTES=30
NUM_RELEVANT_TWEETS=5

# PRODUCTS COMPONENT CONFIGURATION
PRODUCTS_SCHEDULING_MINUTES=360

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

SMFR_IMAGE=efas/smfr_base
GEONAMES_IMAGE=efas/geonames
CASSANDRA_IMAGE=efas/cassandrasmfr
MYSQL_IMAGE=efas/mysql
PERSISTER_IMAGE=efas/persister
ANNOTATOR_IMAGE=efas/annotator
GEOCODER_IMAGE=efas/geocoder
AGGREGATOR_IMAGE=efas/aggregator
PRODUCTS_IMAGE=efas/products
RESTSERVER_IMAGE=efas/restserver
WEB_IMAGE=efas/web
