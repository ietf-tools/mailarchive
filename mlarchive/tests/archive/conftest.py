from django.core.management import call_command
from factories import *
from mlarchive.archive.management.commands._classes import get_base_subject
from StringIO import StringIO

import datetime
import os
import pytest

def load_db():
    pubone = EmailListFactory.create(name='pubone')
    pubtwo = EmailListFactory.create(name='pubtwo')
    prilist = EmailListFactory.create(name='private',private=True)
    athread = ThreadFactory.create(date=datetime.datetime(2013,1,1))
    bthread = ThreadFactory.create(date=datetime.datetime(2013,2,1))
    MessageFactory.create(email_list=pubone,
                          thread=athread,
                          base_subject=get_base_subject('Another message'),
                          date=datetime.datetime(2013,1,1))
    MessageFactory.create(email_list=pubone,
                          thread=bthread,
                          subject='BBQ Invitation',
                          base_subject=get_base_subject('BBQ Invitation'),
                          date=datetime.datetime(2013,2,1),
                          to='to@amsl.com')
    MessageFactory.create(email_list=pubone,
                          thread=bthread,
                          base_subject=get_base_subject('Zero conf stuff'),
                          date=datetime.datetime(2013,3,1))
    MessageFactory.create(email_list=pubone,
                          thread=athread,
                          frm='larry@amsl.com',
                          base_subject=get_base_subject('[RE] BBQ Invitation things'),
                          date=datetime.datetime(2014,1,1),
                          spam_score=1)
    MessageFactory.create(email_list=pubtwo)
    MessageFactory.create(email_list=pubtwo)
    #MessageFactory.create(email_list=pubtwo,date=datetime.datetime(2014,7,1))
    #MessageFactory.create(email_list=pubtwo,date=datetime.datetime(2014,7,1))
    
@pytest.fixture(scope="session")
def index_resource():
    if not Message.objects.first():
        load_db()
    # build index
    content = StringIO()
    call_command('update_index', stdout=content)
    def fin():
        call_command('clear_index', noinput=True, stdout=content)
        print content.read()

@pytest.fixture()
def messages(index_resource):
    """Load some messages into db and index for testing"""
    if not Message.objects.first():
        load_db()

@pytest.fixture(scope="session")
def index():
    """Load a Xapian index"""
    content = StringIO()
    path = os.path.join(settings.BASE_DIR,'tests','data','ancp-2010-03.mail')
    call_command('load', path, listname='ancp', summary=True, stdout=content)
    #def fin():
    #   remove index

'''
@pytest.fixture(scope="session", autouse=True)
def disconnect_signals():
    post_save.disconnect(reindex_month_6_report, sender=Grant)
    post_save.disconnect(reindex_month_12_report, sender=Grant)
    post_save.disconnect(reindex_month_18_report, sender=Grant)
    post_save.disconnect(reindex_month_24_report, sender=Grant)
    post_save.disconnect(reindex_month_30_report, sender=Grant)
'''
