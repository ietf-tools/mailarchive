import datetime
import os
import re
import shutil
import time

from django.core.management.base import BaseCommand, CommandError

from mlarchive.archive.models import EmailList, Legacy
from mlarchive.archive.mail import get_mb, CustomMbox, Loader, UnknownFormat

import logging
logger = logging.getLogger(__name__)

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def guess_list(path):
    """Try to guess the list we are importing based on header values
    """
    mb = get_mb(path)

    # not enough info in MMDF-style mailbox to guess list
    if not isinstance(mb, CustomMbox):
        return None

    if len(mb) == 0:
        return None

    msg = mb[0]
    if msg.get('X-BeenThere'):
        val = msg.get('X-BeenThere').split('@')[0]
        if val:
            return val
    if msg.get('List-Post'):
        val = msg.get('List-Post')
        match = re.match(r'<mailto:(.*)@.*', val)
        if match:
            return match.groups()[0]


def isfile(path):
    """Custom version of os.path.isfile, return True if path is an existing regular file
    and not empty
    """
    if not os.path.isfile(path):
        return False
    statinfo = os.stat(path)
    if statinfo.st_size == 0:
        return False
    return True


# --------------------------------------------------
# Classes
# --------------------------------------------------


class Command(BaseCommand):
    help = 'Imports message(s) into the archive'

    def add_arguments(self, parser):
        parser.add_argument('source')
        parser.add_argument('-b', '--break', action='store_true', dest='break', default=False,
            help='break on error')
        parser.add_argument('-d', '--dry-run', action='store_true', dest='dryrun', default=False,
            help='perform a trial run with no messages saved to db or disk'),
        parser.add_argument('-f', '--format', dest='format',
            help='mailbox format.  accepted values: mbox,mmdf (default is mbox)'),
        parser.add_argument('-l', '--listname', dest='listname',
            help='specify the name of the email list'),
        parser.add_argument('-p', '--private', action='store_true', dest='private', default=False,
            help='private list (default is public)'),
        parser.add_argument('-s', '--summary', action='store_true', dest='summary', default=False,
            help="summarize statistics, for use with aggregator"),
        parser.add_argument('-t', '--test', action='store_true', dest='test', default=False,
            help="test mode.  write database but don't store message files"),
        parser.add_argument('--firstrun', action='store_true', dest='firstrun', default=False,
            help='only use this on the initial import of the archive'),

    def handle(self, *args, **options):
        stats = {}
        source = options['source']
        if options.get('firstrun') and Legacy.objects.all().count() == 0:
            raise CommandError('firstrun specified but the legacy archive table is empty')

        # gather source files
        if os.path.isfile(source):
            files = [source]
        elif os.path.isdir(source):
            FILE_PATTERN = re.compile(r'^\d{4}-\d{2}(|.mail)$')
            mboxs = [f for f in os.listdir(source) if FILE_PATTERN.match(f)]
            # we need to import the files in chronological order so thread resolution works
            sorted_mboxs = sorted(mboxs)
            full = [os.path.join(source, x) for x in sorted_mboxs]
            # exclude directories and empty files
            files = list(filter(isfile, full))
        else:
            raise CommandError("%s is not a file or directory" % source)

        # determine list
        if not options['listname']:
            options['listname'] = guess_list(files[0])
        if not options['listname']:
            raise CommandError("list not specified and not guessable [%s]" % files[0])

        # force listname lowercase
        options['listname'] = options['listname'].lower()

        start_time = time.time()
        for filename in files:
            try:
                loader = Loader(filename, **options)
                loader.process()
                for key, val in list(loader.stats.items()):          # compile stats
                    stats[key] = stats.get(key, 0) + val
            except UnknownFormat as error:
                # save failed message
                if not (options['dryrun'] or options['test']):
                    target = EmailList.get_failed_dir(options['listname'])
                    if not os.path.exists(target):
                        os.makedirs(target)
                    shutil.copy(filename, target)
                logger.error("Import Error [Unknown file format, {0}]".format(error.args))
                stats['unknown'] = stats.get('unknown', 0) + 1

        stats['time'] = int(time.time() - start_time)

        if options.get('summary'):
            return stats.__str__()
        else:
            items = ['%s:%s' % (k, v) for k, v in list(stats.items()) if k != 'time']
            items.append('Elapsed Time:%s' % str(datetime.timedelta(seconds=stats['time'])))
            items.append('\n')
            return '\n'.join(items)
