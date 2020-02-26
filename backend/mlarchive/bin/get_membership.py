#!/a/mailarch/current/env/bin/python
'''
This script checks all active private lists memberships, if membership has changed since
last time it was run, the list membership db table is updated.  This script can be run
periodically by cron.
'''

# Standalone broilerplate -------------------------------------------------------------
from django_setup import do_setup
do_setup()
# -------------------------------------------------------------------------------------

from optparse import OptionParser
from mlarchive.archive.utils import get_membership


def main():
    usage = "usage: %prog"
    parser = OptionParser(usage=usage)
    parser.add_option("-q", "--quiet", help="Don't print lists as they are processed",
                      action="store_true", default=False)
    (options, args) = parser.parse_args()

    get_membership(options, args)


if __name__ == "__main__":
    main()
