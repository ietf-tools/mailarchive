FROM ghcr.io/ietf-tools/mailarchive-app-base:latest
LABEL maintainer="IETF Tools Team <tools-discuss@ietf.org>"

ENV DEBIAN_FRONTEND=noninteractive

# Copy library scripts to execute
ADD https://raw.githubusercontent.com/microsoft/vscode-dev-containers/v0.236.0/containers/python-3/.devcontainer/library-scripts/common-debian.sh /tmp/library-scripts/
ADD https://raw.githubusercontent.com/microsoft/vscode-dev-containers/v0.236.0/containers/python-3/.devcontainer/library-scripts/python-debian.sh /tmp/library-scripts/
ADD https://raw.githubusercontent.com/microsoft/vscode-dev-containers/v0.236.0/containers/python-3/.devcontainer/library-scripts/meta.env /tmp/library-scripts/

# [Option] Install zsh
ARG INSTALL_ZSH="true"
# [Option] Upgrade OS packages to their latest versions
ARG UPGRADE_PACKAGES="true"
# Install needed packages and setup non-root user. Use a separate RUN statement to add your own dependencies.
ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=$USER_UID
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    # Install common packages, non-root user
    && bash /tmp/library-scripts/common-debian.sh "${INSTALL_ZSH}" "${USERNAME}" "${USER_UID}" "${USER_GID}" "${UPGRADE_PACKAGES}" "true" "true"

# Setup default python tools in a venv via pipx to avoid conflicts
ENV PIPX_HOME=/usr/local/py-utils \
    PIPX_BIN_DIR=/usr/local/py-utils/bin
ENV PATH=${PATH}:${PIPX_BIN_DIR}
RUN bash /tmp/library-scripts/python-debian.sh "none" "/usr/local" "${PIPX_HOME}" "${USERNAME}"

# Remove library scripts for final image
RUN rm -rf /tmp/library-scripts

COPY docker/scripts/docker-entrypoint.sh /usr/local/bin/
RUN sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

COPY docker/configs/gunicorn.conf.py /gunicorn.conf.py

# Switch to local dev user
USER dev:dev

# Install current mail archive python dependencies
COPY requirements.txt /tmp/pip-tmp/
RUN pip3 --disable-pip-version-check --no-cache-dir install --user --no-warn-script-location -r /tmp/pip-tmp/requirements.txt
RUN pip3 --disable-pip-version-check --no-cache-dir install --user --no-warn-script-location pylint pylint-common pylint-django
RUN sudo rm -rf /tmp/pip-tmp

# Copy app files
COPY . .

# Copy configuration files
COPY docker/configs/docker_env /workspace/.env
COPY docker/configs/settings_docker.py  \
  /workspace/backend/mlarchive/settings/settings_docker.py

ENTRYPOINT ["docker-entrypoint.sh"]

# runserver
CMD ["./backend/manage.py", "runserver", "0.0.0.0:8000"]

# gunicorn
# CMD ["gunicorn", "-c", "/gunicorn.conf.py", "backend.mlarchive.wsgi:application"]
