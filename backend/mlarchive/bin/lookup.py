'''
Lookup messages in elastic index
'''
import django
django.setup()

import argparse
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from django.conf import settings


def main():
    parser = argparse.ArgumentParser(description='Lookup messages in index')
    parser.add_argument('--msgid', type=str, help="Message ID")
    parser.add_argument('--pk', type=int, help="Message primary key")
    args = parser.parse_args()
    client = Elasticsearch()
    connection_options = settings.ELASTICSEARCH_CONNECTION
    client = Elasticsearch(
        connection_options['URL'],
        index=connection_options['INDEX_NAME'],
        http_auth=connection_options['http_auth'])
    s = Search(using=client, index='mail-archive')
    if args.msgid:
        s = s.query('match', msgid=args.msgid)
        results = s
    elif args.pk:
        s = s.query('match', django_id=args.pk)
        results = s
    else:
        s = s.sort({'django_id': {'order': 'desc'}})[0:1]
        response = s.execute()
        results = [response.hits[0]]
        print('Last message in archive')
    for hit in results:
        print('subject: {}'.format(hit.subject))
        print('from: {}'.format(hit.frm))
        print('date: {}'.format(hit.date))
        print('list: {}'.format(hit.email_list))
        print('\n')


if __name__ == "__main__":
    main()
