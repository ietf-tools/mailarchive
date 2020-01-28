#!../../../env/bin/python
'''
This is a utility script that handles loading multiple list archives.

Note all archives will be loaded as public
'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(django_settings='mlarchive.settings.noindex')
# -------------------------------------------------------------------------------------

from django.core.management import call_command

import argparse
import ast
import datetime
import io
import os
import time


def main():
    parser = argparse.ArgumentParser(description='Import directory of email lists.')
    parser.add_argument('path')
    parser.add_argument('-v','--verbose', help='verbose output',action='store_true')
    parser.add_argument('-t','--test', help='test run',action='store_true')
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        parser.error('{} must be a directory'.format(args.path))

    stats = {}
    start_time = time.time()

    all = [ os.path.join(args.path,x) for x in os.listdir(args.path) ]
    dirs = list(filter(os.path.isdir, all))
    
    for dir in dirs:
        print('Loading: %s' % dir)
        
        # TODO: add option to load private lists
        private = False

        # save output from command so we can aggregate statistics
        content = io.StringIO()
        listname = os.path.basename(dir)

        call_command('load', dir, listname=listname, summary=True,
                     test=args.test, private=private, stdout=content)

        # gather stats from output
        content.seek(0)
        output = content.read()
        results = ast.literal_eval(output)
        for key,val in list(results.items()):
            stats[key] = stats.get(key,0) + val

    elapsed_time = int(time.time() - start_time)
    items = [ '%s:%s' % (k,v) for k,v in list(stats.items()) if k != 'time']
    items.append('Elapsed Time:%s' % str(datetime.timedelta(seconds=elapsed_time)))
    items.append('\n')
    print('\n'.join(items))

if __name__ == "__main__":
    main()
