# FROM --platform=linux/amd64 ghcr.io/ietf-tools/mailarchive-app-base:py312
# FROM --platform=linux/arm64/v8 ghcr.io/ietf-tools/mailarchive-app-base:py312
# FROM ghcr.io/ietf-tools/mailarchive-app-base:py312
FROM ghcr.io/ietf-tools/mailarchive-app-base:py312
LABEL maintainer="IETF Tools Team <tools-discuss@ietf.org>"

ENV DEBIAN_FRONTEND=noninteractive

# [Option] Install zsh
ARG INSTALL_ZSH="true"
# [Option] Upgrade OS packages to their latest versions
ARG UPGRADE_PACKAGES="true"
# Install needed packages and setup non-root user. Use a separate RUN statement to add your own dependencies.
ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=$USER_UID
COPY docker/scripts/app-setup-debian.sh /tmp/library-scripts/docker-setup-debian.sh
RUN sed -i 's/\r$//' /tmp/library-scripts/docker-setup-debian.sh && chmod +x /tmp/library-scripts/docker-setup-debian.sh

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    # Install common packages, non-root user
    # Syntax: ./docker-setup-debian.sh [install zsh flag] [username] [user UID] [user GID] [upgrade packages flag] [install Oh My Zsh! flag] [Add non-free packages]
    && bash /tmp/library-scripts/docker-setup-debian.sh "true" "${USERNAME}" "${USER_UID}" "${USER_GID}" "false" "true" "true"

# Install Node.js from NodeSource (dev only; production image does not need Node).
# Debian's nodejs package is Node 18 without npm, so use NodeSource and pin it
# so the Debian package can never take precedence.
ARG NODE_MAJOR=24
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && printf 'Package: nodejs\nPin: origin deb.nodesource.com\nPin-Priority: 1001\n' > /etc/apt/preferences.d/nodesource \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Setup default python tools in a venv via pipx to avoid conflicts
ENV PIPX_HOME=/usr/local/py-utils \
    PIPX_BIN_DIR=/usr/local/py-utils/bin
ENV PATH=${PATH}:${PIPX_BIN_DIR}

# Remove library scripts for final image
RUN rm -rf /tmp/library-scripts

# Copy the startup file
COPY docker/scripts/app-init.sh /docker-init.sh
RUN sed -i 's/\r$//' /docker-init.sh && \
    chmod +x /docker-init.sh

# Fix user UID / GID to match host
RUN groupmod --gid $USER_GID $USERNAME \
    && usermod --uid $USER_UID --gid $USER_GID $USERNAME \
    && chown -R $USER_UID:$USER_GID /home/$USERNAME \
    || exit 0

# Switch to local dev user
USER dev:dev

# Install current mail archive python dependencies
COPY requirements.txt /tmp/pip-tmp/
RUN pip3 --disable-pip-version-check --no-cache-dir install --user --no-warn-script-location -r /tmp/pip-tmp/requirements.txt
RUN pip3 --disable-pip-version-check --no-cache-dir install --user --no-warn-script-location pylint pylint-common pylint-django
RUN sudo rm -rf /tmp/pip-tmp

# VOLUME [ "/assets" ]
