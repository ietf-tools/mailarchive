from email.utils import parseaddr
from email import policy as email_policy
import datetime
import email
import logging
import os
import re
import subprocess

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils.http import urlencode
from django.template.loader import render_to_string

from mlarchive.archive.generator import Generator
from mlarchive.archive.thread import parse_message_ids
from mlarchive.utils.encoding import is_attachment, custom_policy


TXT2HTML = ['/usr/bin/mhonarc', '-single']
ATTACHMENT_PATTERN = r'<p><strong>Attachment:((?:.|\n)*?)</p>'
REFERENCE_RE = re.compile(r'<(.*?)>')

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def get_in_reply_to_message(in_reply_to_value, email_list):
    '''Returns the in_reply_to message, if it exists'''
    msgids = parse_message_ids(in_reply_to_value)
    if not msgids:
        return None
    return get_message_prefer_list(msgids[0], email_list)


def get_message_from_binary_file(f, policy):
    '''Wrapper function for email.message_from_binary_file. Returns EmailMessage
    unless header parsing fails, else Message
    '''
    msg = email.message_from_binary_file(f, policy=policy)
    try:
        _ = list(msg.items())
        return msg
    except:
        f.seek(0)
        return email.message_from_binary_file(f, policy=email_policy.compat32)


def get_message_prefer_list(msgid, email_list):
    '''Returns Message (or None) prefers proivded list'''
    try:
        return Message.objects.get(msgid=msgid, email_list=email_list)
    except Message.DoesNotExist:
        return Message.objects.filter(msgid=msgid).first()


def is_ascii(text):
    try:
        text.decode('ascii')
    except UnicodeDecodeError:
        return False
    return True


def is_small_year(email_list, year):
    count = Message.objects.filter(email_list=email_list, date__year=year).count()
    return count < settings.STATIC_INDEX_YEAR_MINIMUM


# --------------------------------------------------
# Models
# --------------------------------------------------


class Thread(models.Model):
    date = models.DateTimeField(db_index=True)     # date of first message
    email_list = models.ForeignKey('EmailList', db_index=True, on_delete=models.CASCADE, null=True)
    # first message in thread, by date
    first = models.ForeignKey('Message', on_delete=models.SET_NULL, related_name='thread_key', blank=True, null=True)

    def __str__(self):
        return str(self.id)

    def get_snippet(self):
        """Returns all messages of the thread as an HTML snippet"""
        context = {'messages': self.message_set.all()}
        return render_to_string('archive/thread_snippet.html', context)

    def set_first(self, message=None):
        """Sets the first message of the thread.  Call when adding or removing
        messages
        """
        if not message:
            message = self.message_set.all().order_by('date').first()
        self.first = message
        self.date = message.date
        self.save()

    def get_next(self):
        """Returns next thread in the list"""
        return Thread.objects.filter(email_list=self.email_list, date__gt=self.date).order_by('date').first()

    def get_previous(self):
        """Returns previous thread in the list"""
        return Thread.objects.filter(email_list=self.email_list, date__lt=self.date).order_by('-date').first()


class EmailList(models.Model):
    active = models.BooleanField(default=True, db_index=True)
    alias = models.CharField(max_length=65, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255, blank=True)
    members = models.ManyToManyField(User, blank=True)
    members_digest = models.CharField(max_length=32, blank=True)
    name = models.CharField(max_length=65, db_index=True, unique=True)
    private = models.BooleanField(default=False, db_index=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @staticmethod
    def get_attachments_dir(listname):
        return os.path.join(settings.ARCHIVE_DIR, listname, '_attachments')

    @property
    def attachments_dir(self):
        return self.get_attachments_dir(self.name)

    @staticmethod
    def get_failed_dir(listname):
        return os.path.join(settings.ARCHIVE_DIR, listname, '_failed')

    @property
    def failed_dir(self):
        return self.get_failed_dir(self.name)

    @staticmethod
    def get_removed_dir(listname):
        return os.path.join(settings.ARCHIVE_DIR, listname, '_removed')

    @property
    def removed_dir(self):
        return self.get_removed_dir(self.name)


class Message(models.Model):
    base_subject = models.CharField(max_length=512, blank=True, db_index=True)
    cc = models.TextField(blank=True, default='')
    date = models.DateTimeField(db_index=True)
    email_list = models.ForeignKey(EmailList, db_index=True, on_delete=models.PROTECT)
    frm = models.CharField(max_length=255, blank=True, db_index=True)
    from_line = models.CharField(max_length=255, blank=True)
    hashcode = models.CharField(max_length=28, db_index=True)
    in_reply_to = models.ForeignKey('self', null=True, related_name='replies', on_delete=models.SET_NULL)
    in_reply_to_value = models.TextField(blank=True, default='')
    # mapping to MHonArc message number
    legacy_number = models.IntegerField(blank=True, null=True, db_index=True)
    msgid = models.CharField(max_length=240, db_index=True)
    references = models.TextField(blank=True, default='')
    spam_score = models.IntegerField(default=0)             # > 0 = spam
    subject = models.CharField(max_length=512, blank=True)
    thread = models.ForeignKey(Thread, on_delete=models.PROTECT)
    thread_depth = models.IntegerField(default=0)
    thread_order = models.IntegerField(default=0)
    to = models.TextField(blank=True, default='')
    updated = models.DateTimeField(auto_now=True, db_index=True)
    # date_index_page = models.CharField(max_length=64, default='')
    # thread_index_page = models.CharField(max_length=64, default='')

    class Meta:
        indexes = [models.Index(fields=['email_list', 'date'])]

    def __str__(self):
        return self.msgid

    def as_html(self):
        """Returns the message formated as HTML.  Uses MHonarc standalone
        Not used as of v1.00
        """
        with open(self.get_file_path()) as f:
            mhout = subprocess.check_output(TXT2HTML, stdin=f)

        # extract body
        within = False
        body = []
        for line in mhout.splitlines():
            if line == '<!--X-Body-of-Message-End-->':
                within = False
            if within:
                body.append(line)
            if line == '<!--X-Body-of-Message-->':
                within = True

        str = '\n'.join(body)

        # strip attachment links
        body = re.sub(ATTACHMENT_PATTERN, '', str)

        return body

    @property
    def frm_email(self):
        """This property is the email portion of the "From" header all lowercase
        (the realname is stripped).
        """
        return parseaddr(self.frm)[1].lower()

    @property
    def frm_name(self):
        """This property is the realname portion of the "From" header if it exists.
        Otherwise returns the local-part of the email address
        """
        realname, email = parseaddr(self.frm)
        if realname:
            return realname
        else:
            return email.split('@')[0]

    @property
    def url(self):
        '''Map for index.result.url'''
        return self.get_absolute_url()

    @property
    def django_id(self):
        '''Map for index.result.django_id'''
        return str(self.id)

    @property
    def pymsg(self):
        '''A lazy attribute for the Python message object, email.EmailMessage.
        Use this for direct access to message for headers, body etc.
        '''
        if hasattr(self, '_pymsg'):
            return self._pymsg
        else:
            try:
                with open(self.get_file_path(), 'rb') as f:
                    self._pymsg = get_message_from_binary_file(f, policy=custom_policy)
                    self._pymsg_error = ''
            except IOError:
                logger.error('Error reading message file: %s' % self.get_file_path())
                self._pymsg = None
                self._pymsg_error = 'Error reading message file'
            return self._pymsg
    
    @property
    def pymsg_error(self):
        '''Any errors trying to get Python message, self.pymsg'''
        if not hasattr(self, '_pymsg_error'):
            _ = self.pymsg
        return self._pymsg_error
    
    def get_absolute_url(self):
        # strip padding, "=", to shorten URL
        return reverse('archive_detail', kwargs={
            'list_name': self.email_list.name,
            'id': self.hashcode.rstrip('=')})

    def get_absolute_url_with_host(self):
        # strip padding, "=", to shorten URL
        return settings.ARCHIVE_HOST_URL + reverse('archive_detail', kwargs={
            'list_name': self.email_list.name,
            'id': self.hashcode.rstrip('=')})

    def get_admin_url(self):
        return reverse('archive_admin') + '?' + urlencode(dict(msgid=self.msgid))

    def get_attachment_path(self):
        path = self.email_list.attachments_dir
        if not os.path.exists(path):
            os.makedirs(path)
            os.chmod(path, 0o2777)
        return path

    def get_body(self):
        """Returns the contents of the message body, text only for use in indexing.
        ie. HTML is stripped.  This is called from the index template.
        """
        gen = Generator(self)
        return gen.as_text()

    def get_body_html(self, request=None):
        """Returns the contents of the message body as HTML, for use in display
        """
        gen = Generator(self)
        return gen.as_html(request=request)

    def get_body_raw(self):
        """Returns the raw contents of the message file.
        NOTE: this will include encoded attachments
        """
        try:
            with open(self.get_file_path(), 'rb') as f:
                return f.read()
        except IOError:
            msg = 'Error reading message file: %s' % self.get_file_path()
            logger.error(msg)
            return msg

    def get_date_index_url(self):
        base = reverse('archive_browse_list', kwargs={'list_name': self.email_list.name})
        fragment = '?index={}'.format(self.hashcode.rstrip('='))
        return base + fragment

    def get_reply_url(self):
        '''Return URL to use in Reply-To link for this message'''
        list_post = self.pymsg.get('List-Post')
        if not list_post:
            return ''
        url = list_post.strip('<>')
        subject = self.subject
        if not subject.startswith('Re:'):
            subject = 'Re: ' + subject
        url = url + '?subject=' + subject
        return url

    def get_thread_index_url(self):
        base = reverse('archive_browse_list', kwargs={'list_name': self.email_list.name})
        fragment = '?gbt=1&index={}'.format(self.hashcode.rstrip('='))
        return base + fragment

    def get_static_date_index_url(self):
        return '{url}#{fragment}'.format(
            url=self.get_static_date_page_url(),
            fragment=self.hashcode.rstrip('='),
        )

    def get_static_thread_index_url(self):
        return '{url}#{fragment}'.format(
            url=self.get_static_thread_page_url(),
            fragment=self.hashcode.rstrip('='),
        )

    def get_static_date_page_url(self):
        today = datetime.datetime.today()
        if self.date.year < today.year and is_small_year(self.email_list, self.date.year):
            date = date = '{}'.format(self.date.year)
        else:
            date = '{}-{:02d}'.format(self.date.year, self.date.month)
        return reverse('archive_browse_static_date', kwargs={'list_name': self.email_list.name, 'date': date})

    def get_static_thread_page_url(self):
        today = datetime.datetime.today()
        if self.thread.date.year < today.year and is_small_year(self.email_list, self.thread.date.year):
            date = '{}'.format(self.thread.date.year)
        else:
            date = '{}-{:02d}'.format(self.thread.date.year, self.thread.date.month)
        return reverse('archive_browse_static_thread', kwargs={'list_name': self.email_list.name, 'date': date})

    def get_absolute_static_index_urls(self):
        host_url = settings.ARCHIVE_HOST_URL
        return [host_url + self.get_static_date_page_url(), host_url + self.get_static_thread_page_url()]

    def get_file_path(self):
        return os.path.join(
            settings.ARCHIVE_DIR,
            self.email_list.name,
            self.hashcode)

    def get_from_line(self):
        """Returns the "From " envelope header from the original mbox file if it
        exists or constructs one.  Useful when exporting in mbox format.
        NOTE: returns unicode, call to_str() before writing to file.
        """
        if self.from_line:
            return 'From {}'.format(self.from_line)
        elif self.frm_email:
            return 'From {} {}'.format(
                self.frm_email,
                self.date.strftime('%a %b %d %H:%M:%S %Y'))
        else:
            return 'From (none) {}'.format(
                self.date.strftime('%a %b %d %H:%M:%S %Y'))

    def get_references(self):
        """Returns list of message-ids from References header"""
        # remove all whitespace
        refs = ''.join(self.references.split())
        refs = REFERENCE_RE.findall(refs)
        # de-dupe
        results = []
        for ref in refs:
            if ref not in results:
                results.append(ref)
        return results

    def get_references_messages(self):
        """Returns list of messages from Rerefences header"""
        messages = []
        for msgid in self.get_references():
            message = get_message_prefer_list(msgid, self.email_list)
            if message:
                messages.append(message)
        return messages

    def get_removed_dir(self):
        return self.email_list.removed_dir

    def get_thread_snippet(self):
        """Returns all messages of the thread as an HTML snippet"""
        context = {
            'messages': self.thread.message_set.all().select_related(),
            'msg': self,
        }
        return render_to_string('archive/thread_snippet.html', context)

    def mark(self, bit):
        """Mark this message using the bit provided, using field spam_score
        """
        self.spam_score = self.spam_score | bit
        self.save()

    def next_in_list(self):
        """Return the next message in the list, ordered by date ascending"""
        messages = Message.objects
        messages = messages.filter(email_list=self.email_list, date__gt=self.date)
        messages = messages.order_by('date')
        return messages.first()

    def next_in_thread(self):
        """Return the next message in thread"""
        messages = self.thread.message_set.filter(thread_order__gt=self.thread_order)
        messages = messages.order_by('thread_order')
        if messages.first():
            return messages.first()

        next_thread = Thread.objects.filter(
            date__gt=self.thread.date,
            email_list=self.email_list).order_by('date').first()
        if next_thread:
            return next_thread.message_set.order_by('thread_order').first()
        else:
            return None

    def previous_in_list(self):
        """Return the previous message in the list, ordered by date ascending"""
        messages = Message.objects
        messages = messages.filter(email_list=self.email_list, date__lt=self.date)
        messages = messages.order_by('date')
        return messages.last()

    def previous_in_thread(self):
        """Return the previous message in thread"""
        messages = self.thread.message_set.filter(thread_order__lt=self.thread_order)
        messages = messages.order_by('thread_order')
        if messages.last():
            return messages.last()

        previous_thread = Thread.objects.filter(
            date__lt=self.thread.date,
            email_list=self.email_list).order_by('date').last()
        if previous_thread:
            return previous_thread.message_set.order_by('thread_order').first()
        else:
            return None

    @property
    def thread_date(self):
        """Returns the date of the first message in the associated thread.  Use for
        grouping by Thread
        """
        return self.thread.date

    @property
    def to_and_cc(self):
        """Returns 'To' and 'CC' fields combined, for use in indexing
        """
        if self.cc:
            return self.to + ' ' + self.cc
        else:
            return self.to


class Attachment(models.Model):
    # message if problem with attachment
    error = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=255)
    filename = models.CharField(max_length=65, blank=True, default='')      # old disk filename
    message = models.ForeignKey(Message, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=150)
    content_disposition = models.CharField(max_length=150, blank=True, null=True)
    sequence = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('archive_attachment', kwargs={'list_name': self.message.email_list.name,
                                                     'id': self.message.hashcode.strip('='),
                                                     'sequence': str(self.sequence)})

    def get_file_path(self):
        return os.path.join(self.message.get_atttachment_path(), self.filename)

    def get_sub_message(self):
        """Returns a email.message, that is the attachment"""
        msg = email.message_from_bytes(self.message.get_body_raw())
        parts = list(msg.walk())
        return parts[self.sequence]


class Legacy(models.Model):
    email_list_id = models.CharField(max_length=40)
    msgid = models.CharField(max_length=240, db_index=True)
    number = models.IntegerField()

    def __str__(self):
        return '%s:%s' % (self.email_list_id, self.msgid)


class Subscriber(models.Model):
    email_list = models.ForeignKey(EmailList, db_index=True, on_delete=models.PROTECT)
    date = models.DateField(default=datetime.date.today)
    count = models.PositiveIntegerField()

    def __str__(self):
        return '{}: {}'.format(self.email_list, self.count)


class Redirect(models.Model):
    old = models.CharField(max_length=255, db_index=True, unique=True)
    new = models.CharField(max_length=255)

    def __str__(self):
        return '{} -> {}'.format(self.old, self.new)
