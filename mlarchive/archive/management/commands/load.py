from optparse import make_option
from django.core.management.base import BaseCommand, CommandError
from mlarchive.archive.models import *

import _classes
import _archiver

class Command(BaseCommand):
    args = '<message file>'
    help = 'Imports message(s) into the archive'
    
    option_list = BaseCommand.option_list + (
        make_option('-l', '--listname', dest='listname',
            help='Specify the name of the email list'),
        make_option('-t', '--test',
            action='store_true', dest='test', default=False,
            help="Test mode.  Write databse but don't store message files."),
        )
        
    def handle(self, *args, **options):
        filename = args[0]
        
        if not os.path.exists(filename):
            raise CommandError('File "%s" does not exist' % filename)
        
        loader = _classes.loader(filename, **options)
        loader.startclock()
        
        mb = mailbox.mbox(filename)
        for m in mb:
            loader.load_message(m)
        
        loader.stopclock()
        loader.showstats()
        #self.stdout.write('Successfully imported file "%s"' % filename)
