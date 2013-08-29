from optparse import make_option
from django.core.management.base import BaseCommand, CommandError
from mlarchive.archive.models import *

import _classes

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

def guess_list(path):
    '''
    Determine the list we are importing based on header values
    '''
    mb = get_mb(path)

    # not enough info in MMDF-style mailbox to guess list
    if mb.__class__ == 'mmdf':
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
        match = re.match(r'<mailto:(.*)@.*',val)
        if match:
            return match.groups()[0]

def isfile(path):
    '''
    Custom version of os.path.isfile, return True if path is an existing regular file and not empty
    '''
    if not os.path.isfile(path):
        return False
    statinfo = os.stat(filename)
    if statinfo.st_size == 0:
        return False
    return True

# --------------------------------------------------
# Classes
# --------------------------------------------------

class Command(BaseCommand):
    args = 'SOURCE'
    help = 'Imports message(s) into the archive'

    option_list = BaseCommand.option_list + (
        make_option('-b', '--break', action='store_true', dest='break', default=False,
            help='break on error'),
        make_option('-d', '--dry-run', action='store_true', dest='dryrun', default=False,
            help='perform a trial run with no messages saved to db or disk'),
        make_option('-f', '--format', dest='format',
            help='mailbox format.  accepted values: mbox,mmdf (default is mbox)'),
        make_option('-l', '--listname', dest='listname',
            help='specify the name of the email list'),
        make_option('-p', '--private', action='store_true', dest='private', default=False,
            help='private list (default is public)'),
        make_option('-s', '--summary', action='store_true', dest='test', default=False,
            help="summarize statistics, for use with aggregator"),
        make_option('-t', '--test', action='store_true', dest='test', default=False,
            help="test mode.  write database but don't store message files"),
        make_option('--firstrun', action='store_true', dest='firstrun', default=False,
            help='only use this on the initial import of the archive'),
        )

    def handle(self, *args, **options):
        stats = {}
        # validate options
        if len(args) == 0:
            raise CommandError('source file or directory required')
        source = args[0]
        if options.get('firstrun') and Legacy.objects.all().count() == 0:
            raise CommandError('firstrun specified but the legacy archive table is empty')

        # gather source files
        if os.path.isfile(source):
            files = [source]
        elif os.path.isdir(source):
            FILE_PATTERN = re.compile(r'^\d{4}-\d{2}(|.mail)$')
            mboxs = [ f for f in os.listdir(source) if FILE_PATTERN.match(f) ]
            # we need to import the files in chronological order so thread resolution works
            sorted_mboxs = sorted(mboxs)
            full = [ os.path.join(source,x) for x in sorted_mboxs ]
            # exclude directories and empty files
            files = filter(isfile,full)
        else:
            raise CommandError("%s is not a file or directory" % source)

        # determine list
        listname = options.get('listname')
        if not listname:
            listname = guess_list(files[0])
        if not listname:
            raise CommandError("list not specified and not guessable")

        start_time = time.time()
        for filename in files:
            loader = _classes.Loader(filename, listname, **options)
            loader.process()
            # compile stats
            for key,val in loader.stats.items:
                stats[key] = stats.get(key,0) + val

        stats['time'] = time.time() - start_time

        if options.get('summary'):
            return stats.__str__()
        else:
            output = 'Messages Processed: %d' % stats['count']
            output += 'Errors: %d' % stats['errors']
            output += 'Elapsed Time: %s' % stats['time']
            return output