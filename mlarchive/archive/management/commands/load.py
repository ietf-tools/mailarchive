from optparse import make_option
from django.core.management.base import BaseCommand, CommandError
from mlarchive.archive.models import *

import _classes
import _archiver

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

class Command(BaseCommand):
    args = '<message file>'
    help = 'Imports message(s) into the archive'
    
    option_list = BaseCommand.option_list + (
        make_option('-l', '--listname', dest='listname',
            help='Specify the name of the email list'),
        make_option('-t', '--test', action='store_true', dest='test', default=False,
            help="Test mode.  Write database but don't store message files."),
        make_option('-f', '--format', dest='format',
            help='Mailbox format.  Accepted values: mbox,mmdf'),
        make_option('-p', '--private', action='store_true', dest='private', default=False,
            help='Private list.  Default is public'),
        make_option('--firstrun', action='store_true', dest='firstrun', default=False,
            help='Only use this on the initial import of the archive'),
        )
        
    def handle(self, *args, **options):
        filename = args[0]
        
        if options.get('firstrun') and Legacy.objects.all().count() == 0:
            raise CommandError('ERROR: on firstrun, the leagcy archive index is empty')
        if not os.path.exists(filename):
            raise CommandError('File "%s" does not exist' % filename)
        
        loader = _classes.Loader(filename, **options)
        loader.startclock()
        loader.process()
        loader.stopclock()
        
        return loader.get_stats()
