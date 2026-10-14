<div align="center">

<img src="https://static.ietf.org/logos/icon-mailarchive.svg" alt="IETF Mail Archive" height="125" />

# Mail Archive

[![Release](https://img.shields.io/github/release/ietf-tools/mailarchive.svg?style=flat&maxAge=300)](https://github.com/ietf-tools/mailarchive/releases)
[![License](https://img.shields.io/github/license/ietf-tools/mailarchive?maxAge=3600)](https://github.com/ietf-tools/mailarchive/blob/main/LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.14-blue?logo=python&logoColor=white)](#tech-stack)
[![Django Version](https://img.shields.io/badge/django-5.2-blue?logo=django&logoColor=white)](#tech-stack)
[![PostgreSQL Version](https://img.shields.io/badge/postgres-17-blue?logo=postgresql&logoColor=white)](#tech-stack)
[![Elasticsearch Version](https://img.shields.io/badge/elasticsearch-7.17-blue?logo=elasticsearch&logoColor=white)](#tech-stack)
[![Node Version](https://img.shields.io/badge/node.js-24.x-green?logo=node.js&logoColor=white)](#tech-stack)

##### IETF Mail List Archives

</div>

- [**Production Website**](https://mailarchive.ietf.org)
- [Changelog](https://github.com/ietf-tools/mailarchive/releases)
- [Contributing](https://github.com/ietf-tools/.github/blob/main/CONTRIBUTING.md)

The Mail Archive archives, threads, indexes and serves the messages of every IETF mailing list,
public and private. It holds millions of messages going back decades and provides full-text
search, date and thread browsing, static index pages for CDN caching, mbox exports and a REST
API.

---

- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Development](#development)
- [Running Tests](#running-tests)
- [Frontend Assets](#frontend-assets)
- [Management Commands](#management-commands)
- [API](#api)
- [Repository Layout](#repository-layout)
- [Releases and Deployment](#releases-and-deployment)
- [Further Reading](#further-reading)
- [License](#license)

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Application | Python 3.14, Django 5.2, Gunicorn |
| Databases | PostgreSQL 17 (two databases: application data and message blobs) |
| Search | Elasticsearch 7.17 via `elasticsearch-dsl` |
| Async work | Celery with RabbitMQ, Celery Beat for scheduled jobs |
| Object storage | S3-compatible: MinIO in development, Cloudflare R2 in production |
| Cache | Memcached |
| Frontend | Bootstrap 5, SCSS compiled with Dart Sass (Node.js 24) |
| Edge | Cloudflare CDN and a Cloudflare Worker that serves message pages from R2 |
| Auth | OpenID Connect against auth.ietf.org |

## Architecture

### Message ingestion

```
Mailman
  -> POST /api/v1/message/import/     archive/api.py
  -> stage in ml-messages-incoming, return 201
  -> import_message_blob_task         archive/tasks.py (Celery)
  -> parse and validate               archive/mail.py
  -> spam inspectors                  archive/inspectors.py
  -> hashcode (SHA-1 of Message-ID + list name)
  -> store raw message as a blob      blobdb (PostgreSQL)
  -> save Message, compute threading  archive/models.py, archive/thread.py
  -> on commit: index in Elasticsearch (Celery)
  -> async: replicate blob to R2      blobdb/replication.py
  -> purge affected static pages from the CDN
```

Mailman delivers each message to the import API (`archive/api.py:ImportMessageView`) as a JSON
payload containing the list name, list visibility and the base64-encoded message. The view only
stages the message in the `ml-messages-incoming` bucket and queues a Celery task, which runs
`archive/mail.py:archive_message()`. If staging fails it returns an error and Mailman queues the
message for resubmission.

### Key concepts

- **Hashcode.** Every message is identified by a URL-safe base64 SHA-1 digest of its Message-ID
  and list name (`archive/mail.py:make_hash`). When a Message-ID is reused on a list with
  different content, a digest of the content is mixed in so the two messages stay distinct.
  Message URLs are `/arch/msg/<list>/<hashcode>/`, with the trailing `=` padding stripped; the
  database keeps the padded form.
- **Two databases.** The default database holds lists, messages, threads and users. A separate
  `blobdb` database holds message content as binary blobs and is the source of truth for it.
  `blobdb.routers.BlobDBRouter` routes the `Blob` model there automatically.
- **Blob storage and replication.** All message I/O goes through `archive/storage_utils.py`. A
  dedicated Celery queue (`blobdb`) and worker (`replicator`) copy blobs to R2 asynchronously.
  The `StoredObject` model records metadata (store, name, SHA-384, length) for each object held
  in blob storage.
- **Threading.** Threads are computed with the Zawinski algorithm when a message is saved and
  cached in `thread_order` and `thread_depth`. Displayed indentation is capped at
  `MAX_THREAD_DEPTH` (6) levels.
- **Search.** Queries are built in `archive/query_utils.py` and run against the `mail-archive`
  index. Indexing is synchronous in development and tests (`RealtimeSignalProcessor`) and
  asynchronous through Celery in production (`CelerySignalProcessor`), selected by
  `ELASTICSEARCH_SIGNAL_PROCESSOR`.
- **Private lists.** Lists with `private=True` are restricted to list members. Membership is
  synced periodically from the Mailman API.
- **Static index pages.** Pre-rendered date and thread browse pages under `/arch/browse/static/`
  are cached by Cloudflare and purged when messages are added or removed. See
  [docs/cdn_integration.md](docs/cdn_integration.md).

### Blob buckets

| Bucket | Contents |
|--------|----------|
| `ml-messages` | Public message content |
| `ml-messages-json` | JSON renderings used by the Cloudflare Worker |
| `ml-messages-private` | Private list messages |
| `ml-messages-removed` | Removed messages |
| `ml-messages-incoming` | Staging for incoming messages |
| `ml-messages-filtered`, `ml-messages-spam`, `ml-messages-dupes`, `ml-messages-failed` | Messages kept out of the searchable archive, by reason (failed = import errors) |
| `ml-templates` | Templates for the Cloudflare Worker |

## Development

The development environment runs entirely in Docker Compose ([compose-dev.yml](compose-dev.yml)).

| Service | Purpose |
|---------|---------|
| `app` | Django application, port 8000 |
| `db` | PostgreSQL, application database |
| `blobdb` | PostgreSQL, blob database |
| `es` | Elasticsearch |
| `rabbit` | RabbitMQ |
| `celery` | Celery worker for the default queue |
| `replicator` | Celery worker for the `blobdb` replication queue |
| `blobstore` | MinIO, S3-compatible object storage |
| `memcached` | Cache |
| `worker` | Cloudflare Worker for message pages (`wrangler dev`), port 8787 |

### VS Code Dev Container (recommended)

Open the project in VS Code and choose **Reopen in Container**. The container runs the project
setup on first start. Tasks under **Terminal -> Run Task** include **Run Checks**,
**Run Migrations**, **Run All Tests** and **Re-run Setup Project**.

### Command line

```sh
cd docker && ./run-dev
```

Options: `-p PORT` to serve on a port other than 8000, `-r` to force a rebuild of the app
container. When the containers are up you get a shell inside the app container. Start the
development server with:

```sh
backend/manage.py check && backend/manage.py runserver 0.0.0.0:8000
```

The site is then at <http://localhost:8000>. Leaving the shell stops the containers.

### Configuration

Settings live in `backend/mlarchive/settings/`. `base.py` reads its values from the environment;
`docker-development.py` is used in the dev containers, `test.py` by the test suite and
`settings.py` in production. See [.env.sample](.env.sample) for the full list of environment
variables (databases, Elasticsearch, Celery broker, blob store, Mailman API, OIDC).

### Sample data

To load a few small lists (yang-doctors, mtgvenue, curdle) from the IETF rsync server, run this
inside the app container:

```sh
backend/mlarchive/bin/load_sample_data.sh
```

## Running Tests

From inside the app container:

```sh
cd backend/mlarchive
pytest tests                            # full suite
pytest tests/archive/test_mail.py       # one file
pytest -k threading                     # by name
pytest --cov=mlarchive tests            # with coverage
```

[pytest.ini](backend/mlarchive/pytest.ini) selects `mlarchive.settings.test` and passes
`--reuse-db --nomigrations`. Test data is built with factory-boy factories. Because the test
database is reused, run one pytest invocation at a time.

CI runs the same suite on pull requests that touch the backend or frontend ([.github/workflows/ci-run-tests.yml](.github/workflows/ci-run-tests.yml)).

## Frontend Assets

Styles are SCSS on top of Bootstrap 5:

```sh
cd frontend
npm install
npm run build
```

This writes `bootstrap_custom.css` and `styles.css` to
`backend/mlarchive/static/mlarchive/css/`.

## Management Commands

Run with `backend/manage.py <command>`:

| Command | Purpose |
|---------|---------|
| `init_index` | Create the Elasticsearch index |
| `rebuild_index` | Reindex everything from the database |
| `update_index` | Incremental index update |
| `clear_index` | Remove all documents from the index |
| `rebuild_static_index` | Regenerate the static browse pages |
| `load <mbox>` | Import messages from an mbox file |
| `move_list` | Move messages from one list to another |
| `get_membership` | Sync private list membership from Mailman |
| `get_subscriber_counts` | Record list subscriber counts |
| `create_cf_worker_templates` | Build the templates used by the Cloudflare Worker |

## API

A REST API is served under `/api/v1/` and authenticated with an API key in the `X-API-Key` header.
It covers message import, search and statistics. The OpenAPI specification is in
[api.yml](api.yml).

## Repository Layout

```
backend/
  manage.py
  mlarchive/
    archive/        core app: models, ingestion, threading, views, API
    blobdb/         blob storage and R2 replication
    settings/       per-environment Django settings
    templates/      Django templates
    bin/            maintenance and legacy import scripts
    tests/          pytest suite
frontend/           SCSS sources and build scripts
workers/messages/   Cloudflare Worker serving message pages
docker/             dev Dockerfiles, run-dev and init scripts
build/app/          production image build and start scripts
k8s/                Kubernetes manifests
dev/                sandbox deploy tool and CI helpers
docs/               design and operations notes
```

## Releases and Deployment

The [Build and Release](.github/workflows/build.yml) workflow builds a `release.tar.gz` and a
production Docker image, publishes a GitHub release, and deploys to staging and production.
Production runs on Kubernetes; the manifests in [k8s/](k8s/) define the app (Gunicorn behind
nginx), Celery workers, the replicator, Celery Beat, Elasticsearch, RabbitMQ and Memcached.

The Cloudflare Worker is deployed separately by
[deploy-worker.yml](.github/workflows/deploy-worker.yml).

### Sandbox

Running the Build and Release workflow with the **Deploy to Sandbox** option deploys the build
to the sandbox server. To deploy a release tarball to a container by hand, see
[dev/deploy-to-container/README.md](dev/deploy-to-container/README.md).

## Further Reading

- [docs/cdn_integration.md](docs/cdn_integration.md) - static mode and Cloudflare caching
- [docs/notes_on_infrastructure.md](docs/notes_on_infrastructure.md) - infrastructure notes
- [docs/elasticsearch_snapshots.txt](docs/elasticsearch_snapshots.txt) - Elasticsearch snapshots
- [docs/timezones.md](docs/timezones.md) - date and timezone handling
- [docs/python_email_notes.md](docs/python_email_notes.md) - notes on Python's email package
- [backend/mlarchive/blobdb/README.md](backend/mlarchive/blobdb/README.md) - blobdb app setup
- [workers/messages/README.md](workers/messages/README.md) - the message Worker

## License

BSD 3-Clause, copyright IETF Trust. See [LICENSE](LICENSE).
