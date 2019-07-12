import binascii
import email
import re
import six
from email.header import HeaderParseError
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


'''
This is a customized version of email.header.decode_header, which allows double quote
or right paren at the end of a MIME encoded-word (RFC2047).

TODO: remove when upgrading to 3.x because email now handles this case
'''

SPACE = ' '
# Match encoded-word strings in the form =?charset?q?Hello_World?=
ecre = re.compile(r'''
  =\?                   # literal =?
  (?P<charset>[^?]*?)   # non-greedy up to the next ? is the charset
  \?                    # literal ?
  (?P<encoding>[qb])    # either a "q" or a "b", case insensitive
  \?                    # literal ?
  (?P<encoded>.*?)      # non-greedy up to the next ?= is the encoded string
  \?=                   # literal ?=
  (?=[\s\"\)]|$)           # whitespace, double quote, right paren or the end of the string
  ''', re.VERBOSE | re.IGNORECASE | re.MULTILINE)
#


def decode_header(header):
    """Decode a message header value without converting charset.

    Returns a list of (decoded_string, charset) pairs containing each of the
    decoded parts of the header.  Charset is None for non-encoded parts of the
    header, otherwise a lower-case string containing the name of the character
    set specified in the encoded string.

    An email.errors.HeaderParseError may be raised when certain decoding error
    occurs (e.g. a base64 decoding exception).
    """
    # If no encoding, just return the header
    header = str(header)
    if not ecre.search(header):
        return [(header, None)]
    decoded = []
    dec = ''
    for line in header.splitlines():
        # This line might not have an encoding in it
        if not ecre.search(line):
            decoded.append((line, None))
            continue
        parts = ecre.split(line)
        while parts:
            unenc = parts.pop(0).strip()
            if unenc:
                # Should we continue a long line?
                if decoded and decoded[-1][1] is None:
                    decoded[-1] = (decoded[-1][0] + SPACE + unenc, None)
                else:
                    decoded.append((unenc, None))
            if parts:
                charset, encoding = [s.lower() for s in parts[0:2]]
                encoded = parts[2]
                dec = None
                if encoding == 'q':
                    dec = email.quoprimime.header_decode(encoded)
                elif encoding == 'b':
                    paderr = len(encoded) % 4   # Postel's law: add missing padding
                    if paderr:
                        encoded += '==='[:4 - paderr]
                    try:
                        dec = email.base64mime.decode(encoded)
                    except binascii.Error:
                        # Turn this into a higher level exception.  BAW: Right
                        # now we throw the lower level exception away but
                        # when/if we get exception chaining, we'll preserve it.
                        raise HeaderParseError
                if dec is None:
                    dec = encoded

                if decoded and decoded[-1][1] == charset:
                    decoded[-1] = (decoded[-1][0] + dec, decoded[-1][1])
                else:
                    decoded.append((dec, charset))
            del parts[0:3]
    return decoded
