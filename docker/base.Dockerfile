# syntax=docker/dockerfile:1
FROM python:3.14-slim-trixie
LABEL maintainer="Ryan Cross <rcross@amsl.com>"

# Ensure apt is in non-interactive to avoid prompts
ENV DEBIAN_FRONTEND=noninteractive

# Update system packages. The slim image lacks the tools needed to add apt sources.
RUN apt-get update \
    && apt-get -qy upgrade \
    && apt-get -y install --no-install-recommends apt-utils dialog 2>&1 \
    && apt-get -y install --no-install-recommends ca-certificates curl

# Add Postgresql Apt Repository (deb822 format, https://www.postgresql.org/download/linux/debian/)
RUN <<'EOF'
set -e
install -d -m 0755 /etc/apt/keyrings
curl -fsSL -o /etc/apt/keyrings/postgresql.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc
. /etc/os-release
cat > /etc/apt/sources.list.d/pgdg.sources <<SOURCES
Types: deb
URIs: https://apt.postgresql.org/pub/repos/apt
Suites: ${VERSION_CODENAME}-pgdg
Components: main
Signed-By: /etc/apt/keyrings/postgresql.asc
SOURCES
EOF

# Install the packages we need
RUN apt-get update --fix-missing && apt-get install -qy \
    apache2-utils \
    apt-file \
    bash \
    build-essential \
    curl \
    locales \
    postgresql-client-17 \
    memcached \
    netcat-openbsd \
    rsync \
    rsyslog \
    strace \
    sudo \
    telnet \
    unzip \
    wget \
    zsh

# netcat: for deploy-to-container wait for elasticsearch
# rsync: for deploy-to-container load_messages

# Get rid of installation files we don't need in the image, to reduce size
RUN apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Set locale to en_US.UTF-8
RUN echo "LC_ALL=en_US.UTF-8" >> /etc/environment && \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen && \
    echo "LANG=en_US.UTF-8" > /etc/locale.conf && \
    dpkg-reconfigure locales && \
    locale-gen en_US.UTF-8 && \
    update-locale LC_ALL en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

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
