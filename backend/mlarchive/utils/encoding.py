import binascii
import email
import re
import six
from email.header import HeaderParseError, decode_header
import logging

DEFAULT_CHARSET = 'latin1'
INLINE_MIME_TYPES = ['message/external-body', 'message/delivery-status', 'message/rfc822']

logger = logging.getLogger(__name__)


def decode_rfc2047_header(text):
    try:
        return ' '.join(decode_safely(s, charset) for s, charset in decode_header(text))
    except email.header.HeaderParseError as error:
        logger.warning('Decode header failed [{0},{1}]'.format(error.args, text))
        return ''


def decode_safely(data, charset=DEFAULT_CHARSET):
    """Return data decoded according to charset, but do so safely."""
    if isinstance(data, six.text_type):
        return data
    try:
        #return str(data, charset or DEFAULT_CHARSET)
        return data.decode(charset or DEFAULT_CHARSET)
    except (UnicodeDecodeError, LookupError):
        #return str(data, DEFAULT_CHARSET, errors='replace')
        return data.decode(DEFAULT_CHARSET, errors='replace')


def get_filename(sub_message):
    """Wraps email.message.get_filename(), in Python 2 the function can either return
    str or unicode(when collapse_rfc2231() is used), Python 3 always returns str.
    """
    filename = sub_message.get_filename()
    if isinstance(filename, six.binary_type):
        try:
            filename = filename.decode('ascii')
        except UnicodeDecodeError:
            return ''
    return filename


def is_attachment(sub_message):
    """Returns true if sub_messsage (email.message) is an attachment"""
    content_type = sub_message.get_content_type()
    filename = get_filename(sub_message)
    if filename and content_type not in INLINE_MIME_TYPES:
        return True
    else:
        return False
