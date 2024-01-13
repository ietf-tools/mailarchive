### Notes on Infrastructure

This section describes some of the parts of the system that aren't obvious.

1) How are records added to the index?

When a Message object is saved, the system uses Django Signals to enqueue a Celery task to update the Elasticsearch index. See mlarchive/archive/signals.py, CelerySignalProcessor.  Initialized in archive/apps.py via settings.ELASTICSEARCH_SIGNAL_PROCESSOR.

`CelerySignalProcessor`: when objects are save checks to see if an index exists for them. If so calls task to update index.