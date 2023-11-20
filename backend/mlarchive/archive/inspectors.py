'''This module contains classes which inherit from Inspector.  They are used
to inspect incoming messages and perform some auxiliary processing.  ie. spam
checkers. To enable an inspector add it to the INSPECTORS dictionary setting.
The value of the entry is a dictionary of options.

Supported Options:
"includes": a list of list names to act upon. If not present acts on all lists
'''


from django.conf import settings


class InspectorMessage(Exception):
    pass


class SpamMessage(InspectorMessage):
    pass


class NoArchiveMessage(InspectorMessage):
    pass


class InspectorMeta(type):
    def __init__(cls, name, bases, dct):
        if not hasattr(cls, 'registry'):
            # this is the base class.  Create an empty registry
            cls.registry = {}
        else:
            # this is a derived class.  Add cls to the registry
            interface_id = name.lower()
            cls.registry[interface_id] = cls

        super(InspectorMeta, cls).__init__(name, bases, dct)


class Inspector(object, metaclass=InspectorMeta):
    '''The base class for inspector classes.  Takes a MessageWrapper object and listname
    (string).  Inherit from this class and implement has_condition(), handle_file(),
    raise_error() methods.  Call inspect() to run inspection.'''

    def __init__(self, message_wrapper, options=None):
        self.message_wrapper = message_wrapper
        self.listname = message_wrapper.listname
        if options:
            self.options = options
        else:
            self.options = settings.INSPECTORS.get(self.__class__.__name__)

    def inspect(self):
        if 'includes' in self.options and self.listname not in self.options['includes']:
            return
        if self.has_condition():
            if not self.options.get('check_only'):
                self.handle_file()
            self.raise_error()

    def has_condition(self):
        raise NotImplementedError

    def handle_file(self):
        raise NotImplementedError

    def raise_error(self):
        raise NotImplementedError


class SpamInspector(Inspector):
    '''Base spam handling class.  To write a spam filter, inherit from this class and
    implement has_condition().  Filters will be run on all mail unless a
    settings.INSPECTOR_INLCUDES entry is used'''

    def has_condition(self):
        raise NotImplementedError

    def handle_file(self):
        self.message_wrapper.write_msg(subdir='_spam')

    def raise_error(self):
        raise SpamMessage('Spam Detected.  Message-ID: {}'.format(self.message_wrapper.msgid))


class ListIdSpamInspector(SpamInspector):
    '''Checks for missing or bogus List-Id header (doesn't contain listname).  If so,
    message is spam (has_condition = True)'''
    def has_condition(self):
        listid = self.message_wrapper.email_message.get('List-Id')
        if listid and self.listname in listid:
            return False
        else:
            return True


class ListIdExistsSpamInspector(SpamInspector):
    '''Checks for missing List-Id header.  If so, message is spam (has_condition = True)'''
    def has_condition(self):
        listid = self.message_wrapper.email_message.get('List-Id')
        if listid is None:
            return True
        else:
            return False


class SpamStatusSpamInspector(SpamInspector):
    '''Checks for SpamStatus == Yes'''
    def has_condition(self):
        return self.message_wrapper.email_message.get('X-Spam-Status', '').startswith('Yes')


class SpamLevelSpamInspector(SpamInspector):
    '''Checks for SpamLevel >= *****'''
    def has_condition(self):
        return self.message_wrapper.email_message.get('X-Spam-Level', '').startswith('*****')


class NoArchiveInspector(Inspector):
    '''Checks for no archive headers'''
    def has_condition(self):
        keys = self.message_wrapper.email_message.keys()
        if 'X-No-Archive' in keys:
            return True
        value = self.message_wrapper.email_message.get('X-Archive', '')
        if value.lower() == 'no':
            return True
        return False

    def handle_file(self):
        '''Don't do anything. Drop file'''
        pass

    def raise_error(self):
        raise NoArchiveMessage('X-No-Archive  Message-ID: {}'.format(self.message_wrapper.msgid))


class LongMessageIDSpamInspector(SpamInspector):
    '''Checks if the Message-ID header exceeds max length'''
    def has_condition(self):
        msgid = self.message_wrapper.email_message.get('Message-ID')
        return len(msgid) > 998
