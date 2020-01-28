#!../../../env/bin/python
'''
This script will search for index records that have no corresponding db object.
For best performance set HAYSTACK_ITERATOR_LOAD_PRE_QUERY = 10000
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------


import argparse
import os
from celery_haystack.utils import get_update_task
from django.conf import settings
from haystack.query import SearchQuerySet
from mlarchive.archive.models import *

import logging
logpath = os.path.join(settings.DATA_ROOT, 'log/check_index.log')
logging.basicConfig(filename=logpath, level=logging.DEBUG)


def remove_index_entry(id):
    '''Remove index entry using Celery queued task'''
    task = get_update_task()
    task.delay('delete', id)


def main():
    # parse arguments
    parser = argparse.ArgumentParser(description='Check index for bad records')
    parser.add_argument('-f', '--fix', help="perform fix", action='store_true')
    args = parser.parse_args()

    sqs = SearchQuerySet()
    count = 0
    stat = {}
    for n, sr in enumerate(sqs):
        if n % 10000 == 0:
            logging.info(n)
        if sr.object is None:
            count = count + 1
            logging.warning(sr.id + '\n')
            elist = sr.email_list
            stat[elist] = stat.get(elist, 0) + 1
            if args.fix:
                remove_index_entry(sr.id)
            # _ = input('Return to continue')

    print(count)
    for k, v in list(stat.items()):
        print("{}:{}".format(k, v))


if __name__ == "__main__":
    main()
