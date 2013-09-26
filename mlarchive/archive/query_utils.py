from haystack.query import SQ
from django.conf import settings
from django.utils.log import getLogger
from datetime import datetime, timedelta

import re
import string
import sys

logger = getLogger('mlarchive.custom')

HAYSTACK_DEFAULT_OPERATOR = getattr(settings,'HAYSTACK_DEFAULT_OPERATOR','AND')

# --------------------------------------------------
# RE PATTERNS
# --------------------------------------------------
#FIELD_PATTERN = re.compile(r"^(\w+):(\w+)\s*",re.U)
# re.findall(r'\w+(?:-\w+)+',text)  # match hyphenated word(s)
# HYPHENATED_PATTERN = re.compile(r"^(\w+-\w+")
FIELD_PATTERN = re.compile(r"^(text|date|email_list|from|frm|frm_email|msgid|subject|to|spam_score):([a-zA-Z0-9\.\@\-\_\+\=\$]+)\s*",re.U)
NEGATED_FIELD_PATTERN = re.compile(r"^(\-\w+):([a-zA-Z0-9\.\@\-\_\+\=\$]+)\s*",re.U)
FIELD_EXACT_PATTERN = re.compile(r"^(\w+):\"(.+)\"\s*",re.U)
#SIMPLE_QUERY_PATTERN = re.compile(r"^(\w+)\s*",re.U)
SIMPLE_QUERY_PATTERN = re.compile(r"^(\w+)\-*\s*",re.U)
NEGATED_QUERY_PATTERN = re.compile(r"^(\-\w+)\s*",re.U)
OPERATOR_PATTERN = re.compile(r"^(AND|OR|NOT)\s*",re.U)
QUOTED_TEXT_PATTERN = re.compile(r"^\"(.+?)\"\s*",re.U)

# --------------------------------------------------
# Custom Exceptions
# --------------------------------------------------
class NoMatchingBracketsFound(Exception):
    def __init__(self,value=''):
        self.value = value

    def __str__(self):
        return "Matching brackets were not found: "+self.value

class UnhandledException(Exception):
    def __init__(self,value=''):
        self.value = value
    def __str__(self):
        return self.value

# --------------------------------------------------
# Functions handle URL parameters
# --------------------------------------------------
def get_qdr_time(val):
    '''
    This function expects the value of the qdr search parameter [h,d,w,m,y]
    and returns the corresponding datetime to use in the search filter.
    EXAMPLE: h -> now - one hour
    '''
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
    '''
    This function takes a dictionary from form.cleaned_data and returns
    a dictionary to be used as kwargs for the SearchQuerySet.  This function
    can be used with multiple forms which may not include exactly the same fields,
    so we use the get() method.
    '''
    kwargs = {}
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
    return kwargs

# --------------------------------------------------
# Functions to parse the q field
# --------------------------------------------------
def handle_brackets(sq,q,current=HAYSTACK_DEFAULT_OPERATOR):
    no_brackets = 1
    i=1
    assert q[0]=="("
    while no_brackets and i<len(q):
        if q[i]==")":
            no_brackets-=1
        elif q[i]=="(":
            no_brackets+=1
        i+=1
    if not no_brackets:
        sq.add((parse(q[1:i-1])),current)
    else:
        raise NoMatchingBracketsFound(q)
    return sq, q[i:], HAYSTACK_DEFAULT_OPERATOR

def handle_field_exact_query(sq,q,current=HAYSTACK_DEFAULT_OPERATOR):
    mat = re.search(FIELD_EXACT_PATTERN,q)
    query = mat.group(2)
    # append space if there isn't one in query
    if not re.search(r'\s',query):
        query+=" "
    sq.add(SQ(**{str(mat.group(1)+"__exact"):query}),current)
    q,n = re.subn(FIELD_EXACT_PATTERN,'',q,1)
    return sq,q,HAYSTACK_DEFAULT_OPERATOR

def handle_field_query(sq,q,current=HAYSTACK_DEFAULT_OPERATOR ):
    mat = re.search(FIELD_PATTERN,q)
    field, value = translate(mat.group(1),mat.group(2))
    sq.add(SQ(**{str(field):value}),current)
    q, n = re.subn(FIELD_PATTERN,'',q,1)
    return sq,q, HAYSTACK_DEFAULT_OPERATOR

def handle_negated_field_query(sq,q,current=HAYSTACK_DEFAULT_OPERATOR ):
    mat = re.search(NEGATED_FIELD_PATTERN,q)
    field, value = translate(mat.group(1),mat.group(2))
    sq.add(~SQ(**{str(field):value}),current)
    q, n = re.subn(NEGATED_FIELD_PATTERN,'',q,1)
    return sq,q, HAYSTACK_DEFAULT_OPERATOR

def handle_negated_query(sq,q,current):
    mat = re.search(NEGATED_QUERY_PATTERN,q)
    value = mat.group(1)[1:]        # strip leading dash
    sq.add(~SQ(content=value),HAYSTACK_DEFAULT_OPERATOR)
    q, n = re.subn(NEGATED_QUERY_PATTERN,'',q)
    return sq,q,current

def handle_normal_query(sq,q,current):
    if re.search(OPERATOR_PATTERN,q):
        current = re.search(OPERATOR_PATTERN,q).group(1)
    else:
        mat = re.search(SIMPLE_QUERY_PATTERN,q)
        if current == "NOT":
            sq.add(~SQ(content=mat.group(1)),HAYSTACK_DEFAULT_OPERATOR)
        else:
            sq.add(SQ(content=mat.group(1)),current)
        current = HAYSTACK_DEFAULT_OPERATOR
    q, n = re.subn(SIMPLE_QUERY_PATTERN,'',q)
    return sq,q,current

def handle_quoted_query(sq,q,current):
    mat = re.search(QUOTED_TEXT_PATTERN,q)
    query = mat.group(1)
    # append space if there isn't one in query
    if not re.search(r'\s',query):
        query+=" "
    # punctuation characters are not indexed so replace with spaces
    #replace_punctuation = string.maketrans(string.punctuation, ' '*len(string.punctuation))
    #query = query.translate(replace_punctuation)
    query = translate_non_alphanumerics(query)

    sq.add(SQ(content__exact=query),current)
    q,n = re.subn(QUOTED_TEXT_PATTERN,'',q,1)
    return sq,q,HAYSTACK_DEFAULT_OPERATOR

def parse(q):
    '''
    This function takes a search query string and returns a Haystack query.  It accepts
    field specifiers in the form of FIELD:VALUE or -FIELD:VALUE (NOT in).  It also accepts
    boolean search operators AND, OR, NOT.
    '''
    try:
        sq= SQ()
        current = HAYSTACK_DEFAULT_OPERATOR

        # pre-process: convert hyphenated words to quoted phrase without hyphens
        terms = re.findall(r'\w+(?:-\w+)+',q)
        if terms:
            terms.sort(key=len,reverse=True)    # start with longest word first
            for term in terms:
                new = '"%s"' % term.replace('-',' ')
                q = q.replace(term,new)
                #print q

        while q:
            q=q.lstrip()
            if re.search(NEGATED_FIELD_PATTERN,q):
                sq, q, current = handle_negated_field_query(sq,q,current)
            elif re.search(FIELD_PATTERN,q):
                sq, q, current = handle_field_query(sq,q,current)
            elif re.search(FIELD_EXACT_PATTERN,q):
                sq, q, current = handle_field_exact_query(sq,q,current)
            elif re.search(QUOTED_TEXT_PATTERN,q):
                sq, q, current = handle_quoted_query(sq,q,current)
            elif re.search(NEGATED_QUERY_PATTERN,q):
                sq, q,current = handle_negated_query(sq,q,current)
            elif re.search(SIMPLE_QUERY_PATTERN,q):
                sq, q,current = handle_normal_query(sq,q,current)
            elif q[0]=="(":
                sq, q,current = handle_brackets(sq,q,current)
            else:
                q=q[1:]
    except IOError:
        raise UnhandledException(sys.exc_info()[0])
    return sq

def translate(field,value):
    '''
    This function takes two strings that are the field and value derived from a field query
    (ie.  'frm:rcross@amsl.com') and performs specific translations to optimize search.
    Field names that start with a dash are negated field lookups, NOT in, we need to strip
    the dash when returning the field name.
    '''
    # if searching for an email address use the frm_email field
    logger.info('Translation field:%s value:%s' % (field,value))

    if field.startswith('-'):       # strip dash in negated field lookups
        field = field[1:]
    if field == 'from':
        field = 'frm'
    if field == 'frm' and value.find('@') != -1:
        field = 'frm_email'

    return field,value

def translate_non_alphanumerics(to_translate, translate_to=u' '):
    not_letters_or_digits = u'!"#%\'()*+,-./:;<=>?@[\]^_`{|}~'
    translate_table = dict((ord(char), translate_to) for char in not_letters_or_digits)
    return to_translate.translate(translate_table)