import pytest
from django.test.client import RequestFactory
from factories import *
from mlarchive.archive.utils import get_noauth

@pytest.mark.django_db(transaction=True)
def test_get_noauth():
    user = UserFactory.create(username='noauth')
    public = EmailListFactory.create(name='public')
    private1 = EmailListFactory.create(name='private1',private=True)
    private2 = EmailListFactory.create(name='private2',private=True)
    private1.members.add(user)
    factory = RequestFactory()
    request = factory.get('/arch/search/?q=dummy')
    request.user = user
    setattr(request,'session',{})
    lists = get_noauth(request)
    assert len(lists) == 1
    assert lists == [ str(private2.pk) ]