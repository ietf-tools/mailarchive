#!../../../env/bin/python
'''
Update secondary mbox archive with current messages

Example:
./update_mbox_archive.py --month=1 --year=2018

'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

import argparse
import os

from django.conf import settings
from mlarchive.archive.models import EmailList
from mlarchive.archive.utils import create_mbox_file


def month_year_iter(start_month, start_year, end_month, end_year):
    ym_start= 12 * start_year + start_month - 1
    ym_end= 12 * end_year + end_month - 1
    for ym in range(ym_start, ym_end):
        y, m = divmod(ym, 12)
        yield y, m+1


def build_mbox(month, year, elist, verbose=False):
    if verbose:
        print('Building {:04d}-{:02d} {}'.format(year, month, elist.name))
    queryset = elist.message_set.filter(date__month=month, date__year=year)
    if bool(queryset):
        create_mbox_file(month=month, year=year, elist=elist)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--month', help="enter the month to update")
    parser.add_argument('-y', '--year', help="enter the year to update")
    parser.add_argument('--list', help='restrict update to list')
    parser.add_argument('-i', '--init', action='store_true', help='initialize the mbox archive')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose')
    args = parser.parse_args()

    if not args.init and not (args.year and args.month):
        raise Exception('You must specifiy year and month (unless using --init)')
        
    if args.list:
        lists = EmailList.objects.filter(name=args.list, private=False)
    else:
        lists = EmailList.objects.filter(private=False)

    if args.init:
        for elist in lists:
            messages = elist.message_set.order_by('date')
            if messages.count() == 0:
                continue
            first = messages.first()
            last = messages.last()
            for y, m in month_year_iter(first.date.month, first.date.year, last.date.month, last.date.year):
                build_mbox(month=m, year=y, elist=elist, verbose=args.verbose)
    else:
        for elist in lists:
            build_mbox(month=int(args.month), year=int(args.year), elist=elist, verbose=args.verbose)


if __name__ == "__main__":
    main()
