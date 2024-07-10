FROM docker.elastic.co/elasticsearch/elasticsearch:7.17.21

RUN bin/elasticsearch-plugin install --batch repository-azure