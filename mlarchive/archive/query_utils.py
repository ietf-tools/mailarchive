from datetime import datetime, timedelta

from django.conf import settings
from haystack.query import SQ

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Functions handle URL parameters
# --------------------------------------------------
def get_qdr_time(val):
    """Expects the value of the qdr search parameter [h,d,w,m,y]
    and returns the corresponding datetime to use in the search filter.
    EXAMPLE: h -> now - one hour
    """
    now = datetime.now()
    if val == 'h':
        return now - timedelta(hours=1)
    elif val == 'd':
        return now - timedelta(days=1)
    elif val == 'w':
        return now - timedelta(weeks=1)
    elif val == 'm':
        return now - timedelta(days=30)
    elif val == 'y':
        return now - timedelta(days=365)

def get_kwargs(data):
    """Returns a dictionary to be used as kwargs for the SearchQuerySet, data is
    a dictionary from form.cleaned_data and .  This function can be used with multiple
    forms which may not include exactly the same fields, so we use the get() method.
    """
    kwargs = {}
    spam_score = data.get('spam_score')
    for key in ('msgid',):
        if data.get(key):
            kwargs[key] = data[key]
    if data.get('start_date'):
        kwargs['date__gte'] = data['start_date']
    if data.get('end_date'):
        kwargs['date__lte'] = data['end_date']
    if data.get('email_list'):
        kwargs['email_list__in'] = data['email_list']
    if data.get('frm'):
        if '@' in data['frm']:
            kwargs['frm_email'] = data['frm']
        else:
            kwargs['frm__icontains'] = data['frm']
    if data.get('qdr') and data['qdr'] not in ('a','c'):
        kwargs['date__gte'] = get_qdr_time(data['qdr'])
    if data.get('subject'):
        kwargs['subject__icontains'] = data['subject']
    if data.get('spam'):
        kwargs['spam_score__gt'] = 0
    if spam_score and spam_score.isdigit():
        bits = [ x for x in range(255) if x & int(spam_score)]
        kwargs['spam_score__in'] = bits
    return kwargs

