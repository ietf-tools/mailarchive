FROM ghcr.io/ietf-tools/mailarchive-app-base:latest
LABEL maintainer="IETF Tools Team <tools-discuss@ietf.org>"

# set python path
ENV PYTHONPATH "${PYTHONPATH}:/workspace/backend"
ENV DJANGO_SETTINGS_MODULE="mlarchive.settings.settings"

# install dependencies first for image layer reuse
COPY requirements.txt .
RUN pip3 --disable-pip-version-check --no-cache-dir install -r requirements.txt

COPY . .

# Copy configuration files
COPY ./build/app/start.sh ./start.sh
COPY ./build/app/mailarchive-start.sh ./mailarchive-start.sh
COPY ./build/app/celery-start.sh ./celery-start.sh
COPY ./docker/configs/docker_env /workspace/.env
COPY ./docker/configs/settings_docker.py  \
  /workspace/backend/mlarchive/settings/settings_docker.py

RUN chmod +x start.sh && \
    chmod +x mailarchive-start.sh && \
    chmod +x celery-start.sh && \
    chmod +x docker/scripts/app-create-dirs.sh && \
    sh ./docker/scripts/app-create-dirs.sh

# VOLUME

# document the port the container listens on
# EXPOSE 8000

# Switch to local dev user
# USER dev:dev

CMD ["./start.sh"]
