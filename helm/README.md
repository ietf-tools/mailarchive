# Helm Chart Templates for IETF Mail Archive in Kubernetes

## Dependencies

The following subcharts are included:
* elasticsearch
* memcached
* rabbitmq
* postgresql (dev only)

## Production install command
```
helm install \
--set database.host=mailarchive-postgresql,database.name=mailarchive \
--set database.user=some_user,database.password=some_password \
mailarchive chartmuseum/mailarchive
```

## Dev install command
```
helm install --set image.tag=2.23.19 -f helm/values_dev.yaml mailarchive helm 
```
