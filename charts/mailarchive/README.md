# Helm Chart Templates for IETF Mail Archive in Kubernetes

## Prerequisites

Using the template Helm charts assumes the following pre-requisites are complete:

1. Install helm dependency repos
```sh
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add elastic https://helm.elastic.co
```

2. Build dependencies
```sh
helm dependency build
```

## Running (use latest tag)
```sh
helm install --set image.tag=2.22.0 mailarchive charts/mailarchive
```
