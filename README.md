<div align="center">
  
<img src="https://raw.githubusercontent.com/ietf-tools/common/main/assets/logos/mailarch.svg" alt="IETF Mail Archive" height="125" />

[![Release](https://img.shields.io/github/release/ietf-tools/mailarch.svg?style=flat&maxAge=300)](https://github.com/ietf-tools/mailarch/releases)
[![License](https://img.shields.io/github/license/ietf-tools/mailarch?maxAge=3600)](https://github.com/ietf-tools/mailarch/blob/main/LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.9-blue?logo=python&logoColor=white)](#prerequisites)
[![Django Version](https://img.shields.io/badge/django-4.2-blue?logo=django&logoColor=white)](#prerequisites)
[![Node Version](https://img.shields.io/badge/node.js-16.x-green?logo=node.js&logoColor=white)](#prerequisites)
[![MySQL Version](https://img.shields.io/badge/postgres-14.6-blue?logo=postgresql&logoColor=white)](#prerequisites)

##### IETF Mail List Archives

</div>

- [**Production Website**](https://mailarchive.ietf.org)
- [Changelog](https://github.com/ietf-tools/mailarch/releases)
- [Contributing](https://github.com/ietf-tools/.github/blob/main/CONTRIBUTING.md)
- [Development](#development)
  - [Prerequisites](#prerequisites)
  - [Running Tests](#running-tests)
- [Notes on Infrastructures](#notes-on-infrastructure)
- [CDN Integration](#cdn-integration)

---

### Development

What follows are instructions for setting up a development environment on macOS. These instructions were tested on a MacBook Pro running macOS 10.13.6 (High Sierra).

#### Prerequisites

- PostgreSQL 14.6
- Node.js 16.x
- Python 3.9

#### Running Tests

From the root of the project working directory:

```sh
export PYTHONPATH=$PWD
cd backend/mlarchive
py.test tests
py.test --flakes archive
py.test --pep8 archive
```

### Test Server

Follow these instructions to deploy a containerized version of the system on a test server.

- Download release tarbal from GitHub and extract
- run ./docker/run-dev

### Notes on Infrastructure

This section describes some of the parts of the system that aren't obvious.

1) How are records added to the index?

When a Message object is saved, the system uses Django Signals to enqueue a Celery task to update the Elasticsearch index. See mlarchive/archive/signals.py, CelerySignalProcessor.  Initialized in archive/apps.py via settings.ELASTICSEARCH_SIGNAL_PROCESSOR.

`CelerySignalProcessor`: when objects are save checks to see if an index exists for them. If so calls task to update index.

### CDN Integration *(Cloudflare)*

As of `v1.12.4`, mail archive supports a "Static Mode" which resembles the MHonArc interface.
When enabled, from the Settings menu, the user is directed to `/arch/browse/static/` pages.
Cloudflare has been configured to cache these pages for `CACHE_CONTROL_MAX_AGE`.
