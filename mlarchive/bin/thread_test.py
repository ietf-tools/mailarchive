#!/usr/bin/python
'''
Script to test threading functions on archive.
'''
# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(settings='production')
# -------------------------------------------------------------------------------------

import argparse
import time

from mlarchive.archive.models import Message, EmailList
from mlarchive.archive.thread import process

def timeit(method):
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()

        print '%r (%r, %r) %2.2f sec' % \
              (method.__name__, args, kw, te-ts)
        return result

    return timed

@timeit
def do_thread(elist, args):
    queryset = Message.objects.filter(email_list=elist).order_by('date')
    # DEBUG
    #ids = ['55ADF8D7.1000608@meinberg.de', '613F85B8-20E2-45AB-A1D9-1CACC5B82F64@noao.edu']
    #queryset = Message.objects.filter(email_list__name='ntp',subject__contains='Proposed REFID changes').order_by('date')
    #queryset = Message.objects.filter(email_list__name='ntp',msgid__in=ids).order_by('date')
    if not queryset:
        return

    root=process(queryset, debug=args.verbose)
    
    # check walk
    count = 0
    empty = 0
    for c in root.walk():
        count = count + 1
        if c.is_empty():
            empty = empty + 1

    print "Messages: {}, Containers: {}, Empty {}".format(
        queryset.count(),
        count,
        empty)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose mode')
    parser.add_argument('-s', '--start', help='the list to start with')
    parser.add_argument('-l', '--list', help='the list to process')
    args = parser.parse_args()
    kwargs = {}
    if args.list:
        kwargs['name'] = args.list
    if args.start:
        kwargs['name__gte'] = args.start

    elists = EmailList.objects.filter(**kwargs).order_by('name')
    for elist in elists:
        do_thread(elist, args)


if __name__ == "__main__":
    main()
