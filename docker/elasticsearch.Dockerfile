FROM docker.elastic.co/elasticsearch/elasticsearch:7.17.21

RUN bin/elasticsearch-plugin install --batch repository-azure

# Copy the startup file
COPY docker/scripts/elasticsearch-init.sh /docker-init.sh
RUN sed -i 's/\r$//' /docker-init.sh && \
    chmod +x /docker-init.sh

ENTRYPOINT ["/bin/tini", "--", "/docker-init.sh"]