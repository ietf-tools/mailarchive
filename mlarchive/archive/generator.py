import mailbox

from bs4 import BeautifulSoup

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

DEFAULT_CHARSET = 'us-ascii'
UNDERSCORE = '_'

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------
def get_charset(part):
    '''
    Get the character set from the Content-Type.
    Use DEFAULT CHARSET if it isn't set.
    '''
    charset = part.get_content_charset()
    return charset if charset else DEFAULT_CHARSET

def skip_attachment(function):
    '''
    This is a decorator for custom MIME part handlers, handle_*.
    If the part passed is an attachment then it is skipped (None is returned).
    '''
    def _inner(*args, **kwargs):
        if args[1].get_filename():
            return None
        return function(*args, **kwargs)
    return _inner

# --------------------------------------------------
# Classes
# --------------------------------------------------

class Generator:
    '''
    Generates output from a Message object tree.

    Based on email.generator.Generator.  Takes a mlarchive Message object

    msg: mlarchive Message
    mdmsg: mailbox.MaildirMessage
    '''

    def __init__(self, msg):
        self.msg = msg
        self.text_only = False
        try:
            with open(msg.get_file_path()) as f:
                self.mdmsg = mailbox.MaildirMessage(f)
        except IOError:
            return 'Error reading message'


    def as_html(self, request):
        self.text_only = False
        return self.parse_body(request=request)

    def as_text(self):
        self.text_only = True
        return self.parse_body()

    def _dispatch(self,part):
        # Get the Content-Type: for the message, then try to dispatch to
        # self._handle_<maintype>_<subtype>().  If there's no handler for the
        # full MIME type, then dispatch to self._handle_<maintype>().  If
        # that's missing too, then skip it.
        main = part.get_content_maintype()
        sub = part.get_content_subtype()
        specific = UNDERSCORE.join((main, sub)).replace('-', '_')
        meth = getattr(self, '_handle_' + specific, None)
        if meth is None:
            generic = main.replace('-', '_')
            meth = getattr(self, '_handle_' + generic, None)
            if meth is None:
                #meth = self._writeBody
                return None
        meth(part)

    def _handle_message_external_body(self,part):
        '''
        Two common formats:
        A) in content type parameters
        Content-Type: Message/External-body; name="draft-ietf-alto-reqs-03.txt";
            site="ftp.ietf.org"; access-type="anon-ftp";
            directory="internet-drafts"

        Content-Type: text/plain
        Content-ID: <2010-02-17021922.I-D@ietf.org>

        B) as an attachment
        Content-Type: message/external-body; name="draft-howlett-radsec-knp-01.url"
        Content-Description: draft-howlett-radsec-knp-01.url
        Content-Disposition: attachment; filename="draft-howlett-radsec-knp-01.url";
            size=92; creation-date="Mon, 14 Mar 2011 22:39:25 GMT";
            modification-date="Mon, 14 Mar 2011 22:39:25 GMT"
        Content-Transfer-Encoding: base64

        W0ludGVybmV0U2hvcnRjdXRdDQpVUkw9ZnRwOi8vZnRwLmlldGYub3JnL2ludGVybmV0LWRyYWZ0
        cy9kcmFmdC1ob3dsZXR0LXJhZHNlYy1rbnAtMDEudHh0DQo=
        '''
        if self.text_only:
            return None

        # handle B format
        if part.get_filename() and part.get_filename().endswith('url'):
            codec = part['Content-Transfer-Encoding']
            inner = part.get_payload()
            payload = inner[0].get_payload()
            link = payload.decode(codec)
            return link
        # handle A format
        else:
            rawsite = part.get_param('site')
            site = collapse_rfc2231_value(rawsite)
            rawdir = part.get_param('directory')
            dir = collapse_rfc2231_value(rawdir)
            rawname = part.get_param('name')
            name = collapse_rfc2231_value(rawname)
            link = 'ftp://%s/%s/%s' % (site,dir,name)
            html = '<div><a rel="nofollow" href="%s">&lt;%s&gt;</a></div>' % (link,link)
            return html

    @skip_attachment
    def _handle_text_plain(self,part):
        charset = get_charset(part)
        payload = part.get_payload(decode=True)
        if charset not in US_CHARSETS and charset not in UNSUPPORTED_CHARSETS:
            try:
                payload = payload.decode(charset)
            except UnicodeDecodeError as error:
                logger.warn("UnicodeDecodeError [{0}, {1}]".format(error.encoding,error.reason))
                payload = unicode(payload,DEFAULT_CHARSET,errors='ignore')
            except LookupError as error:
                logger.warn("Decode Error [{0}, {1}]".format(error.args,error.message))
                payload = unicode(payload,DEFAULT_CHARSET,errors='ignore')

        result = render_to_string('archive/message_plain.html', {'payload': payload})
        # undeclared charactersets can cause problems with template rendering
        # if result is empty template (len=28) try again with unicode
        if len(result) == 28 and not isinstance(payload, unicode):
            payload = unicode(payload,DEFAULT_CHARSET,errors='ignore')
            result = render_to_string('archive/message_plain.html', {'payload': payload})
        return result

    @skip_attachment
    def _handle_text_html(self,part):
        '''
        Handler for text/HTML MIME parts.  Takes a message.message part
        '''
        if not self.text_only:
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset()
            uni = unicode(payload,charset or DEFAULT_CHARSET,errors='replace')
            return render_to_string('archive/message_html.html', {'payload': uni})
        else:
            payload = part.get_payload(decode=True)
            uni = unicode(payload,errors='ignore')
            # tried many solutions here
            # text = strip_tags(part.get_payload(decode=True)) # problems with bad html
            # soup = BeautifulSoup(part.get_payload(decode=True)) # errors with lxml
            # text = html2text(uni) # errors with malformed tags
            soup = BeautifulSoup(part.get_payload(decode=True),'html5') # included "html" and css
            text = soup.get_text()

            return text

    def parse_body(self, request=None):

        headers = self.mdmsg.items()
        parts = self.parse_entity(self.mdmsg)

        if not self.text_only:
            return render_to_string('archive/message.html', {
                'msg': self.msg,
                'maildirmessage': self.mdmsg,
                'headers': headers,
                'parts': parts,
                'request': request}
            )
        else:
            return '\n'.join(parts)

    def parse_entity(self, entity):
        '''
        This function recursively traverses a MIME email and returns a list of email.Message objects
        '''
        #print "calling parse %s:%s" % (entity.__class__,entity.get_content_type())
        parts = []
        # messages with type message/external-body are marked multipart, but we need to treat them
        # otherwise
        if entity.is_multipart() and entity.get_content_type() != 'message/external-body':
            if entity.get_content_type() == 'multipart/alternative':
                contents = entity.get_payload()
                # NOTE: rather than trying to handle possibly malformed HTML, just use the
                # text/plain versions for display.
                # --clip
                # if output is not for indexing start from the most detailed option
                # if not text_only:
                #     contents = contents[::-1]
                # --clip
                for x in contents:
                    # only return first readable item
                    r = self.parse_entity(x)
                    if r:
                        parts.extend(r)
                        break
            else:
                for part in entity.get_payload():
                    parts.extend(parse_entity(part))
        else:
            body = self._dispatch(entity)
            if body:
                parts.append(body)

        #print "returning parse %s:%s" % (type(parts),parts)
        return parts