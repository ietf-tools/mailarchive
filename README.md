<div align="center">
  
<img src="https://raw.githubusercontent.com/ietf-tools/common/main/assets/logos/mailarch.svg" alt="IETF Mail Archive" height="125" />

[![Release](https://img.shields.io/github/release/ietf-tools/mailarch.svg?style=flat&maxAge=300)](https://github.com/ietf-tools/mailarch/releases)
[![License](https://img.shields.io/github/license/ietf-tools/mailarch?maxAge=3600)](https://github.com/ietf-tools/mailarch/blob/main/LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)](#prerequisites)
[![Django Version](https://img.shields.io/badge/django-4.2-blue?logo=django&logoColor=white)](#prerequisites)
[![Node Version](https://img.shields.io/badge/node.js-16.x-green?logo=node.js&logoColor=white)](#prerequisites)
[![MySQL Version](https://img.shields.io/badge/postgres-14.6-blue?logo=postgresql&logoColor=white)](#prerequisites)

##### IETF Mail List Archives

</div>

- [**Production Website**](https://mailarchive.ietf.org)
- [Changelog](https://github.com/ietf-tools/mailarch/releases)
- [Contributing](https://github.com/ietf-tools/.github/blob/main/CONTRIBUTING.md)
- [Development](#development)
- [Sandbox Server](#sandbox-server)


---

### Development

#### VSCode

This project supports VSCode Dev Containers. Open the project in VSCode and choose restart in container. To run tests: Terminal -> Run Task -> Run All Tests

#### Others

Run `(cd docker && ./run-dev)` from the command line. You will be prompted with the following message.

```text
You can execute arbitrary commands now, e.g.,

    backend/manage.py check && backend/manage.py runserver 0.0.0.0:8000

to start a development instance of the Mail Archive.

    cd backend/mlarchive && pytest tests

to run all the tests.
```

Run `cd backend/mlarchive && pytest tests` to run all tests.

### Sandbox Server

Follow these instructions to deploy a containerized version of the system on a staging server.

- Download release tarbal from GitHub and extract
```sh
mkdir 2.20.12
cd 2.20.12
wget https://github.com/ietf-tools/mailarchive/releases/download/2.20.12/release.tar.gz
tar xvzf release.tar.gz
```
- Run compose
```sh
docker compose -f compose-sandbox.yml up -d
``` 

#### Load sample data

To load some sample data (messages for a few small lists), from within the app container:
```sh
cd backend/mlarchive/bin
./load_sample_data.sh
```
