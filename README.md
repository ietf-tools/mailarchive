<div align="center">
  
<img src="https://raw.githubusercontent.com/ietf-tools/common/main/assets/logos/mailarch.svg" alt="IETF Mail Archive" height="125" />

[![Release](https://img.shields.io/github/release/ietf-tools/mailarch.svg?style=flat&maxAge=300)](https://github.com/ietf-tools/mailarch/releases)
[![License](https://img.shields.io/github/license/ietf-tools/mailarch)](https://github.com/ietf-tools/mailarch/blob/main/LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.6-blue?logo=python&logoColor=white)](#prerequisites)
[![Django Version](https://img.shields.io/badge/django-3.2-51be95?logo=django&logoColor=white)](#prerequisites)
[![Node Version](https://img.shields.io/badge/node.js-16.x-green?logo=node.js&logoColor=white)](#prerequisites)
[![MySQL Version](https://img.shields.io/badge/mysql-5.6-blue?logo=mysql&logoColor=white)](#prerequisites)

##### IETF Mail List Archives

</div>

- [**Production Website**](https://mailarchive.ietf.org)
- [Changelog](https://github.com/ietf-tools/mailarch/blob/main/CHANGELOG.md)
- [Contributing](https://github.com/ietf-tools/.github/blob/main/CONTRIBUTING.md)
- [Development](#development)
  - [Prerequisites](#prerequisites)
  - [Running Tests](#running-tests
- [Notes on Infrastructures](#notes-on-infrastructure)
- [CDN Integration](#cdn-integration)

---

### Development

What follows are instructions for setting up a development environment on macOS. These instructions were tested on a MacBook Pro running macOS 10.13.6 (High Sierra).

#### Prerequisites

- MySQL 5.6
- Node.js 16.x
- Python 3.6

#### Running Tests

From the root of the project working directory:

```sh
export PYTHONPATH=$PWD
cd backend/mlarchive
py.test tests
py.test --flakes archive
py.test --pep8 archive
```

### Notes on Infrastructure

This section describes some of the parts of the system that aren't obvious.

1) How are records added to the index?

In `settings.py` is a setting:
`HAYSTACK_SIGNAL_PROCESSOR = 'celery_haystack.signals.CelerySignalProcessor'`

`haystack/__init__.py` uses this to setup Django signals to save records to the index when models are saved.

`CelerySignalProcessor`: when objects are save checks to see if an index exists for them. If so calls task to update index.

### CDN Integration *(Cloudflare)*

As of `v1.12.4`, mail archive supports a "Static Mode" which resembles the MHonArc interface.
When enabled, from the Settings menu, the user is directed to `/arch/browse/static/` pages.
Cloudflare has been configured to cache these pages for `CACHE_CONTROL_MAX_AGE`.
