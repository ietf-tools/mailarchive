# Dockerfile for celery worker
#
FROM ghcr.io/ietf-tools/mailarchive-app-base:latest
LABEL maintainer="IETF Tools Team <tools-discuss@ietf.org>"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get purge -y imagemagick imagemagick-6-common

# Copy the startup file
COPY docker/scripts/celery-init.sh /docker-init.sh
RUN sed -i 's/\r$//' /docker-init.sh && \
    chmod +x /docker-init.sh

# Install current datatracker python dependencies
COPY requirements.txt /tmp/pip-tmp/
RUN pip3 --disable-pip-version-check --no-cache-dir install -r /tmp/pip-tmp/requirements.txt
RUN rm -rf /tmp/pip-tmp

# Add watchmedo utility for dev containers
RUN pip3 --disable-pip-version-check --no-cache-dir install watchdog[watchmedo]

# Copy app files
COPY . .

# Copy settings
COPY docker/configs/docker_env /workspace/.env

ENTRYPOINT [ "/docker-init.sh" ]