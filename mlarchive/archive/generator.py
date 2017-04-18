""" Generator - a class to generate text or html from mlarchive.archive.Message object

General Notes

email.message.Message.get_payload(decode=True) will decode the message based on the
Content-Transfer-Encoding header.  Common values are quoted-printable, base64, 8bit,
7bit.  The values 8bit and 7bit imply no encoding has been done.  Returns a string,
still possibly encoded using the Content-Type charset.

string.decode(codec) decodes a string according to the codec provided.  Returns a
unicode object.
"""
from email.utils import collapse_rfc2231_value
import mailbox

from bs4 import BeautifulSoup
from django.conf import settings
from django.template.loader import render_to_string
from django.conf import settings
from lxml.etree import XMLSyntaxError, ParserError
from lxml.html.clean import Cleaner

from mlarchive.utils.encoding import decode_safely

import logging
logger = logging.getLogger('mlarchive.custom')

UNDERSCORE = '_'
MESSAGE_RFC822_BEGIN = '<blockquote>\n<small>---&nbsp;<i>Begin&nbsp;Message</i>&nbsp;---</small>'
MESSAGE_RFC822_END = '<small>---&nbsp;<i>End&nbsp;Message</i>&nbsp;---</small>\n</blockquote>'

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------

def skip_attachment(function):
    """This is a decorator for custom MIME part handlers, handle_*.
    If the part passed is an attachment then it is skipped (None is returned).
    """
    def _inner(*args, **kwargs):
        if args[1].get_filename():
            return None
        return function(*args, **kwargs)
    return _inner

# --------------------------------------------------
# Classes
# --------------------------------------------------

class Generator:
    """Generates output from a Message object tree.

    Based on email.generator.Generator.  Takes a mlarchive Message object

    msg: mlarchive Message
    mdmsg: mailbox.MaildirMessage
    text_only: used when generating index data, do not include html markup or headers
    """
    def __init__(self, msg):
        self.msg = msg
        self.text_only = False
        self.error = None
        try:
            with open(msg.get_file_path()) as f:
                self.mdmsg = mailbox.MaildirMessage(f)
        except IOError:
            logger.warning('Error reading message file: %s' % msg.get_file_path())
            self.error = 'Error reading message file'

    def as_html(self, request):
        self.text_only = False
        if self.error:
            return self.error
        else:
            return self.parse_body(request=request)

    def as_text(self):
        """Return only text, no markup, for use in indexing"""
        self.text_only = True
        if self.error:
            return self.error
        else:
            return self.parse_body()

    @staticmethod
    def _clean_headers(headers):
        """Return headers decoded.  Takes a 2-tuple (the output of
        email.message.Message.items()) and returns a list of tuples.
        """
        return [ (k,decode_safely(v)) for k,v in headers ]

    def _dispatch(self,part):
        """Get the Content-Type: for the message, then try to dispatch to
        self._handle_<maintype>_<subtype>().  If there's no handler for the
        full MIME type, then dispatch to self._handle_<maintype>().  If
        that's missing too, then skip it.
        """
        main = part.get_content_maintype()
        sub = part.get_content_subtype()
        specific = UNDERSCORE.join((main, sub)).replace('-', '_')
        meth = getattr(self, '_handle_' + specific, None)
        if meth is None:
            generic = main.replace('-', '_')
            meth = getattr(self, '_handle_' + generic, None)
            if meth is None:
                return None
        return meth(part)

    def _get_decoded_payload(self,part):
        """Returns the decoded payload.

        - first decode using Content-Transfer-Encoding
        - then decode using the Content-Type charset or DEFAULT_CHARSET
        """
        charset = part.get_content_charset()
        payload = part.get_payload(decode=True)
        return decode_safely(payload, charset)

    # multipart handlers ----------------------------------------------------------

    def _handle_message_external_body(self,part):
        """Handler for Message/External-body

        Two common supported formats:
        A) in content type parameters
        Content-Type: Message/External-body; name="draft-ietf-alto-reqs-03.txt";
            site="ftp.ietf.org"; access-type="anon-ftp";
            directory="internet-drafts"

        B) as an attachment
        Content-Type: message/external-body; name="draft-howlett-radsec-knp-01.url"
        Content-Description: draft-howlett-radsec-knp-01.url
        Content-Disposition: attachment; filename="draft-howlett-radsec-knp-01.url";
            size=92; creation-date="Mon, 14 Mar 2011 22:39:25 GMT";
            modification-date="Mon, 14 Mar 2011 22:39:25 GMT"
        Content-Transfer-Encoding: base64

        TODO:
        - there are A/B types that don't conform to this model.  see:
        - B: abfab:hCAW0Vg4mRA_TJC0iievdbPQGBo=
        - B: pk=61273
        - A: pk=167492
        At this time other access-types are not supported (MAIL-SERVER)
        """
        if self.text_only:
            return None

        # handle B format
        if part.get_filename() and part.get_filename().endswith('url'):
            codec = part['Content-Transfer-Encoding']
            inner = part.get_payload()
            payload = inner[0].get_payload()
            try:
                return payload.decode(codec)
            except (UnicodeDecodeError,LookupError):
                return None

        # handle A format
        if part.get_param('access-type') == 'anon-ftp':
            rawsite = part.get_param('site')
            rawdir = part.get_param('directory')
            rawname = part.get_param('name')
            if None in (rawsite,rawdir,rawname):
                return None
            site = collapse_rfc2231_value(rawsite)
            directory = collapse_rfc2231_value(rawdir)
            name = collapse_rfc2231_value(rawname)
            link = 'ftp://%s/%s/%s' % (site,directory,name)
            html = '<div><a rel="nofollow" href="%s">&lt;%s&gt;</a></div>' % (link,link)
            return html
        return None

    def _handle_message_rfc822(self,entity):
        """Handler for message/rfc822.
        Insert HTML beginning and ending tags
        """
        parts = []
        if not self.text_only:
            parts.append(MESSAGE_RFC822_BEGIN)
        for part in entity.get_payload():
            parts.extend(self.parse_entity(part))
        if not self.text_only:
            parts.append(MESSAGE_RFC822_END)
        return parts

    def _handle_multipart(self,entity):
        """Generic multipart handler"""
        parts = []
        
        # Corrupt boundaries may cause a mutlipart entity's get_payload() to return
        # the rest of the message as a string rather than the expected list of MIME
        # entities
        if not isinstance(entity.get_payload(), list):
            return self._handle_text_plain(entity)
            
        for part in entity.get_payload():
            parts.extend(self.parse_entity(part))
        return parts
        
    def _handle_multipart_alternative(self,entity):
        """Handler for multipart/alternative.
        NOTE: rather than trying to handle possibly malformed HTML, prefer the
        text/plain versions for display, which comes first.  Basically return first
        parsable item.
        """
        parts = []
        
        # Corrupt boundaries may cause a mutlipart entity's get_payload() to return
        # the rest of the message as a string rather than the expected list of MIME
        # entities
        if not isinstance(entity.get_payload(), list):
            return self._handle_text_plain(entity)

        for part in entity.get_payload():
            r = self.parse_entity(part)
            if r:
                parts.extend(r)
                break
        return parts

    # non-multipart handlers ----------------------------------------------------------

    @skip_attachment
    def _handle_text_plain(self,part):
        """Handler for text/plain MIME parts.  Takes a message.Message part"""
        if settings.DEBUG:
            logger.debug('called: _handle_text_plain [{0}]'.format(self.msg.msgid))

        payload = self._get_decoded_payload(part)
        if self.text_only:
            return payload
        else:
            return render_to_string('archive/message_plain.html', {'payload': payload})

    @skip_attachment
    def _handle_text_html(self,part):
        """Handler for text/HTML MIME parts.  Takes a message.Message part"""
        if settings.DEBUG:
            logger.debug('called: _handle_text_html [{0}, {1}]'.format(self.msg.email_list,self.msg.msgid))

        payload = self._get_decoded_payload(part)

        # clean html document of unwanted elements (html,script,style,etc)
        cleaner = Cleaner(scripts=True,meta=True,page_structure=True,style=True,
                          remove_tags=['body'],forms=True,frames=True,add_nofollow=True)
        try:
            clean = cleaner.clean_html(payload)
        except (XMLSyntaxError, ParserError) as error:
            logger.error('Error cleaning HTML body [{}, {}, {}]'.format(self.msg.email_list,self.msg.msgid,error.args))
            if self.text_only:
                return None
            else:
                return '<< invalid HTML >>'

        if self.text_only:
            soup = BeautifulSoup(clean,'html5')
            clean = soup.get_text()

        return clean

    # end handlers ----------------------------------------------------------

    def parse_body(self, request=None):
        """Using internal or external function, convert a MIME email object to a string.
        """
        headers = self.mdmsg.items()
        if settings.USE_EXTERNAL_PROCESSOR:
            parts = [self.msg.as_html()]
        else:
            parts = self.parse_entity(self.mdmsg)

        if not self.text_only:
            context = {'msg': self.msg,
                       'maildirmessage': self.mdmsg,
                       'headers': headers,
                       'parts': parts,
                       'request': request}

            # this function is called every time a message is viewed, frequently.
            # to save time try with unmodified headers, which will work 99.9% of
            # time.  Sometimes, ie. spam, header fields will contain non-ASCII
            # characters and we need to clean.
            try:
                body = render_to_string('archive/message.html', context)
            except UnicodeDecodeError:
                context['headers'] = self._clean_headers(headers)
                body = render_to_string('archive/message.html', context)
        else:
            body = '\n'.join(parts)

        return body

    def parse_entity(self, entity):
        """Recursively traverses parts of a MIME email and returns a list of strings
        """
        parts = []
        output = self._dispatch(entity)
        if output:
            if hasattr(output,'__iter__'):
                parts.extend(output)
            else:
                parts.append(output)

        return parts
