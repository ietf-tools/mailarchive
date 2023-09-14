import datetime
import logging
import multiprocessing
import os
import time

from datetime import timedelta
from dateutil.parser import isoparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, reset_queries
from django.utils.encoding import smart_bytes
from django.utils.timezone import now
from elasticsearch_dsl import Search

from mlarchive.archive.models import Message
from mlarchive.archive.backends.elasticsearch import ESBackend

LOG = multiprocessing.log_to_stderr(level=logging.WARNING)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 1000
DEFAULT_AGE = None
DEFAULT_MAX_RETRIES = 5


def do_update(backend, qs, start, end, total, verbosity=1, commit=True,
              max_retries=DEFAULT_MAX_RETRIES, last_max_pk=None):

    logger.debug('do_update() called. backend={}, qs={}'.format(
        type(backend), qs.count()))

    # Get a clone of the QuerySet so that the cache doesn't bloat up
    # in memory. Useful when reindexing large amounts of data.
    small_cache_qs = qs.all()

    # If we got the max seen PK from last batch, use it to restrict the qs
    # to values above; this optimises the query for Postgres as not to
    # devolve into multi-second run time at large offsets.
    if last_max_pk is not None:
        current_qs = small_cache_qs.filter(pk__gt=last_max_pk)[:end - start]
    else:
        current_qs = small_cache_qs[start:end]

    # Remember maximum PK seen so far
    max_pk = None
    current_qs = list(current_qs)
    if current_qs:
        max_pk = current_qs[-1].pk

    if verbosity >= 2:
        print("  indexed %s - %d of %d." % (start + 1, end, total))
        
    retries = 0
    while retries < max_retries:
        try:
            backend.update(current_qs, commit=commit)
            if verbosity >= 2 and retries:
                print('Completed indexing {} - {}, tried {}/{} times'.format(
                    start + 1,
                    end,
                    retries + 1,
                    max_retries))
            break
        except Exception as exc:
            # Catch all exceptions which do not normally trigger a system exit, excluding SystemExit and
            # KeyboardInterrupt.
            retries += 1

            error_context = {'start': start + 1,
                             'end': end,
                             'retries': retries,
                             'max_retries': max_retries,
                             'pid': os.getpid(),
                             'exc': exc}

            error_msg = 'Failed indexing %(start)s - %(end)s (retry %(retries)s/%(max_retries)s): %(exc)s'

            if retries >= max_retries:
                LOG.error(error_msg, error_context, exc_info=True)
                raise
            elif verbosity >= 2:
                LOG.warning(error_msg, error_context, exc_info=True)

            # If going to try again, sleep a bit before
            time.sleep(2 ** retries)

    # Clear out the DB connections queries because it bloats up RAM.
    reset_queries()
    return max_pk


class Command(BaseCommand):
    help = "Freshens the index for the given app(s)."

    def add_arguments(self, parser):
        parser.add_argument(
            '-a', '--age', type=int, default=DEFAULT_AGE,
            help='Number of hours back to consider objects new.'
        )
        parser.add_argument(
            '-s', '--start', dest='start_date',
            help='The start date for indexing in UTC. Use format YYYY-MM-DDTHH:MM'
        )
        parser.add_argument(
            '-e', '--end', dest='end_date',
            help='The end date for indexing in UTC. Use format YYYY-MM-DDTHH:MM'
        )
        parser.add_argument(
            '-b', '--batch-size', dest='batchsize', type=int, default=1000,
            help='Number of items to index at once.'
        )
        parser.add_argument(
            '-r', '--remove', action='store_true', default=False,
            help='Remove objects from the index that are no longer present in the database.'
        )
        parser.add_argument(
            '--nocommit', action='store_false', dest='commit',
            default=True, help='Will pass commit=False to the backend.'
        )

    def handle(self, **options):
        self.verbosity = int(options.get('verbosity', 1))
        self.batchsize = options.get('batchsize')
        self.start_date = None
        self.end_date = None
        self.remove = options.get('remove', False)
        self.workers = options.get('workers', 0)
        self.commit = options.get('commit', True)
        self.max_retries = options.get('max_retries', DEFAULT_MAX_RETRIES)

        age = options.get('age', DEFAULT_AGE)
        start_date = options.get('start_date')
        end_date = options.get('end_date')

        if self.verbosity > 2:
            LOG.setLevel(logging.DEBUG)
        elif self.verbosity > 1:
            LOG.setLevel(logging.INFO)

        if age is not None:
            self.start_date = now() - timedelta(hours=int(age))

        if start_date is not None:
            try:
                sdate = isoparse(start_date)
                self.start_date = sdate.astimezone(datetime.timezone.utc)
            except ValueError:
                raise CommandError('Invalid date {}'.format(start_date))

        if end_date is not None:
            try:
                edate = isoparse(end_date)
                self.end_date = edate.astimezone(datetime.timezone.utc)
            except ValueError:
                raise CommandError('Invalid date {}'.format(end_date))

        try:
            self.update_backend()
        except:
            LOG.exception("Error updating archive index")
            raise

    def update_backend(self):
        backend = ESBackend()
        
        # handle date range
        kwargs = {}
        if self.start_date:
            kwargs['date__gte'] = self.start_date
        if self.end_date:
            kwargs['date__lte'] = self.end_date

        qs = Message.objects.filter(**kwargs).order_by('id')
        total = qs.count()

        logger.info('updating index. kwargs={}, count={}'.format(
            kwargs, total))

        if self.verbosity >= 1:
            self.stdout.write("Indexing {} Messages".format(total))

        batch_size = self.batchsize

        max_pk = None
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)

            max_pk = do_update(backend, qs, start, end, total,
                               verbosity=self.verbosity,
                               commit=self.commit, max_retries=self.max_retries,
                               last_max_pk=max_pk)
            logger.debug('max_pk: {}'.format(max_pk))

        if self.remove:
            if self.start_date or self.end_date or total <= 0:
                # They're using a reduced set, which may not incorporate
                # all pks. Rebuild the list with everything.
                qs = Message.objects.all().values_list('pk', flat=True)
                database_pks = set(smart_bytes(pk) for pk in qs)
            else:
                database_pks = set(smart_bytes(pk) for pk in qs.values_list('pk', flat=True))

            # Since records may still be in the search index but not the local database
            # we'll use that to create batches for processing.
            s = Search(using=backend.client, index=settings.ELASTICSEARCH_INDEX_NAME)
            index_total = s.count()

            # Retrieve PKs from the index. Note that this cannot be a numeric range query because although
            # pks are normally numeric they can be non-numeric UUIDs or other custom values. To reduce
            # load on the search engine, we only retrieve the pk field, which will be checked against the
            # full list obtained from the database, and the id field, which will be used to delete the
            # record should it be found to be stale.
            s = Search(using=backend.client, index=settings.ELASTICSEARCH_INDEX_NAME)
            s = s.source(fields={'includes': ['django_id', 'id']})
            s = s.scan()
            index_pks = [(h['django_id'], h['id']) for h in s]
            # index_pks = SearchQuerySet(using=backend.connection_alias).models(model)
            # index_pks = index_pks.values_list('pk', 'id')

            # We'll collect all of the record IDs which are no longer present in the database and delete
            # them after walking the entire index. This uses more memory than the incremental approach but
            # avoids needing the pagination logic below to account for both commit modes:
            stale_records = set()

            for start in range(0, index_total, batch_size):
                upper_bound = start + batch_size

                # If the database pk is no longer present, queue the index key for removal:
                for pk, rec_id in index_pks[start:upper_bound]:
                    if smart_bytes(pk) not in database_pks:
                        stale_records.add(rec_id)

            if stale_records:
                if self.verbosity >= 1:
                    self.stdout.write("  removing %d stale records." % len(stale_records))

                for rec_id in stale_records:
                    # Since the PK was not in the database list, we'll delete the record from the search
                    # index:
                    if self.verbosity >= 2:
                        self.stdout.write("  removing %s." % rec_id)

                    backend.remove(rec_id, commit=self.commit)
