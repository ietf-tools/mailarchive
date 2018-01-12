import email

DEFAULT_CHARSET = 'latin1'

import logging
logger = logging.getLogger('mlarchive.custom')

def decode_rfc2047_header(text):
    try:
        return ' '.join(decode_safely(s, charset) for s, charset in email.header.decode_header(text))
    except email.header.HeaderParseError as error:
        logger.error('Decode header failed [{0},{1}]'.format(error.args,text))
        return ''

def decode_safely(data, charset=DEFAULT_CHARSET):
    """Return data decoded according to charset, but do so safely."""
    try:
        return unicode(data,charset or DEFAULT_CHARSET)
    except (UnicodeDecodeError, LookupError):
        return unicode(data,DEFAULT_CHARSET,errors='replace')

def to_str(unicode_or_str):
    """Return byte string given unicode or string object"""
    if isinstance(unicode_or_str, unicode):
        value = unicode_or_str.encode('utf-8')
    else:
        value = unicode_or_str
    return value    # Instance of str
