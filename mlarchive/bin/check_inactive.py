#!/usr/bin/python
from __future__ import print_function

'''
Script to retrieve active lists, identify inactive lists, and update the db

'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup(settings='production')
# -------------------------------------------------------------------------------------

import argparse
from mlarchive.archive.utils import check_inactive


def main():
    parser = argparse.ArgumentParser(description='Check for inactive lists')
    parser.add_argument('--noinput', action='store_true', help="Don't prompt to update inactive lists")
    args = parser.parse_args()
    check_inactive(prompt=not args.noinput)


if __name__ == "__main__":
    main()
