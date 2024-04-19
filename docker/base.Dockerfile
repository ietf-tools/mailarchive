FROM python:3.9-bullseye
LABEL maintainer="Ryan Cross <rcross@amsl.com>"

# Ensure apt is in non-interactive to avoid prompts
ENV DEBIAN_FRONTEND=noninteractive

# Update system packages
RUN apt-get update \
    && apt-get -qy upgrade \
    && apt-get -y install --no-install-recommends apt-utils dialog 2>&1

# Add Postgresql Apt Repository to get 14 
RUN echo "deb http://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo "$VERSION_CODENAME")-pgdg main" | tee /etc/apt/sources.list.d/pgdg.list
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -

# Install the packages we need
RUN apt-get update --fix-missing && apt-get install -qy \
    apache2-utils \
    apt-file \
    bash \
    build-essential \
    curl \
    locales \
    postgresql-client-14 \
    memcached \
    nodejs \
    rsyslog \
    sudo \
    telnet \
    unzip \
    wget \
    zsh

# purge because of vulnerability (see https://www.cvedetails.com/)
RUN apt-get purge -y imagemagick imagemagick-6-common

# Get rid of installation files we don't need in the image, to reduce size
# this should be included in install layer above if chromedriver layer removed
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Set locale to en_US.UTF-8
RUN echo "LC_ALL=en_US.UTF-8" >> /etc/environment && \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
    echo "LANG=en_US.UTF-8" > /etc/locale.conf && \
    dpkg-reconfigure locales && \
    locale-gen en_US.UTF-8 && \
    update-locale LC_ALL en_US.UTF-8
ENV LC_ALL en_US.UTF-8

# Fetch wait-for utility
ADD https://raw.githubusercontent.com/eficode/wait-for/v2.1.3/wait-for /usr/local/bin/
RUN chmod +rx /usr/local/bin/wait-for

# Create a dev user and group with a specific UID/GID
RUN groupadd --gid 1000 dev \
    && useradd --uid 1000 --gid dev --shell /bin/bash --create-home dev

# Create data directory
RUN mkdir -p /data

# Create workspace
RUN mkdir -p /workspace
WORKDIR /workspace
