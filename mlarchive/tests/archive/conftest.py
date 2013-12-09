import pytest
from factories import *

@pytest.fixture(scope="module")
def messages():
    "Load some messages into db and index for testing"
    publist = EmailListFactory.create(name='public')
    prilist = EmailListFactory.create(name='private',private=True)
    athread = ThreadFactory.create()
    bthread = ThreadFactory.create()
    MessageFactory.create(email_list=publist,thread=athread,hashcode='00001')
    MessageFactory.create(email_list=prilist,thread=bthread,hashcode='00002')

'''
@pytest.fixture(scope="session", autouse=True)
def disconnect_signals():
    post_save.disconnect(reindex_month_6_report, sender=Grant)
    post_save.disconnect(reindex_month_12_report, sender=Grant)
    post_save.disconnect(reindex_month_18_report, sender=Grant)
    post_save.disconnect(reindex_month_24_report, sender=Grant)
    post_save.disconnect(reindex_month_30_report, sender=Grant)
'''