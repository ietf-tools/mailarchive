FROM python:3.9-bullseye
LABEL maintainer="Ryan Cross <rcross@amsl.com>"

ENV DEBIAN_FRONTEND=noninteractive

# Update system packages
RUN apt-get update \
    && apt-get -qy upgrade \
    && apt-get -y install --no-install-recommends apt-utils dialog 2>&1

# Install the packages we need
RUN apt-get update --fix-missing && apt-get install -qy \
    apache2-utils \
    apt-file \
    bash \
    build-essential \
    curl \
    locales \
    postgresql-client \
    memcached \
    nodejs \
    rsyslog \
    unzip \
    wget \
    zsh

# Install chromedriver
COPY docker/scripts/app-install-chromedriver.sh /tmp/app-install-chromedriver.sh
RUN sed -i 's/\r$//' /tmp/app-install-chromedriver.sh && \
    chmod +x /tmp/app-install-chromedriver.sh
RUN /tmp/app-install-chromedriver.sh

# "fake" dbus address to prevent errors
# https://github.com/SeleniumHQ/docker-selenium/issues/87
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null

# Set locale to en_US.UTF-8
RUN echo "LC_ALL=en_US.UTF-8" >> /etc/environment && \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
    echo "LANG=en_US.UTF-8" > /etc/locale.conf && \
    dpkg-reconfigure locales && \
    locale-gen en_US.UTF-8 && \
    update-locale LC_ALL en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# Create data directory
RUN mkdir -p /data

# Create workspace
RUN mkdir -p /workspace
WORKDIR /workspace
