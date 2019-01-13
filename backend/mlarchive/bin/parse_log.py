#!/usr/bin/python

'''
Script to analyze apache logs of mail archive and gather statistics on response times
'''

import argparse
import numpy
import re
from operator import itemgetter
import sys

APACHE_RE = re.compile(r'(?P<ip>.*?) (?P<remote_log_name>.*?) (?P<userid>.*?) \[(?P<date>.*?)(?= ) (?P<timezone>.*?)\] \"(?P<request_method>.*?) (?P<path>.*?)(?P<request_version> HTTP/.*)?\" (?P<status>.*?) (?P<length>.*?) \*\*(?P<generation_time_sec>\d+)/(?P<generation_time_micro>\d+)\*\*')
DATA = []
EXPORT_DATA = []


def parse_line(line, exclude=None):
    match = APACHE_RE.match(line)
    if match:
        if exclude and exclude in line:
            pass
        elif 'export' in line:
            EXPORT_DATA.append(match.groupdict())
        else:
            DATA.append(match.groupdict())


def main():
    parser = argparse.ArgumentParser(description='Produce response stats from apache log file')
    parser.add_argument('file')
    parser.add_argument('-u', '--urls', help='print urls', action='store_true')
    parser.add_argument("--exclude", help="Exclude lines containing term", default='')
    args = parser.parse_args()

    with open(args.file) as file:
        print "Inspecting %s" % args.file
        for line in file.readlines():
            parse_line(line, exclude=args.exclude)

    data = filter(lambda x: x['path'].startswith('/arch/'), DATA)
    response = sorted(data, key=lambda x: int(itemgetter("generation_time_sec")(x)), reverse=True)

    if args.urls:
        for line in data:
            print "%s" % line['path']
        sys.exit()

    if args.exclude:
        print "Excluded: {}".format(args.exclude)
    print "Records processed: %d" % len(DATA)
    print "Searches processed: %d" % len(data)
    nums = [int(x['generation_time_sec']) for x in response]
    print nums[:25]
    print "Mean: %s" % numpy.mean(nums)
    print "Median: %s" % numpy.median(nums)

    for item in response[:30]:
        print "{} {}".format(item['path'], item['generation_time_sec'])


if __name__ == "__main__":
    main()
