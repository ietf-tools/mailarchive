import datetime
import pytest

from django.urls import reverse
from factories import EmailListFactory, MessageFactory
from mlarchive.archive.models import Subscriber

@pytest.mark.django_db(transaction=True)
def test_msg_counts_one_list(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&start=20130101'
     response = client.get(url)
     data = response.json()
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 5


@pytest.mark.django_db(transaction=True)
def test_msg_counts_two_lists(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone,pubtwo&start=20130101'
     response = client.get(url)
     data = response.json()
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 5
     assert 'pubtwo' in data['msg_counts']
     assert data['msg_counts']['pubtwo'] == 2


@pytest.mark.django_db(transaction=True)
def test_msg_counts_unknown_list(client, messages):
     url = reverse('api_msg_counts') + '?list=balloons&start=20130101'
     response = client.get(url)
     data = response.json()
     assert response.status_code == 404
     assert data == {'error': 'list not found'}


@pytest.mark.django_db(transaction=True)
def test_msg_counts_private_list(client, messages):
     url = reverse('api_msg_counts') + '?list=private&start=20130101'
     response = client.get(url)
     data = response.json()
     assert response.status_code == 404
     assert data == {'error': 'list not found'}


@pytest.mark.django_db(transaction=True)
def test_msg_counts_no_list(client, messages):
     '''Should return all public lists, no private'''
     url = reverse('api_msg_counts') + '?start=20130101'
     response = client.get(url)
     data = response.json()
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 5
     assert 'pubtwo' in data['msg_counts']
     assert data['msg_counts']['pubtwo'] == 2
     assert 'private' not in data['msg_counts']


@pytest.mark.django_db(transaction=True)
def test_msg_counts_no_date(client, messages):
     '''If no date provided return last month'''
     pubfour = EmailListFactory.create(name='pubfour')
     date = datetime.datetime.now().replace(second=0, microsecond=0)
     MessageFactory.create(email_list=pubfour, date=date - datetime.timedelta(days=14))
     MessageFactory.create(email_list=pubfour, date=date - datetime.timedelta(days=35))
     url = reverse('api_msg_counts') + '?list=pubfour'
     response = client.get(url)
     data = response.json()
     assert 'pubfour' in data['msg_counts']
     assert data['msg_counts']['pubfour'] == 1


@pytest.mark.django_db(transaction=True)
def test_msg_counts_start(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&start=20130601'
     response = client.get(url)
     data = response.json()
     assert 'start' in data
     assert data['start'] == '20130601'
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 2


@pytest.mark.django_db(transaction=True)
def test_msg_counts_start_bad(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&start=142'
     response = client.get(url)
     data = response.json()
     assert response.status_code == 400
     assert data == {'error': 'invalid start date'}


@pytest.mark.django_db(transaction=True)
def test_msg_counts_end(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&start=20130101&end=20130601'
     response = client.get(url)
     data = response.json()
     assert 'end' in data
     assert data['end'] == '20130601'
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 3


@pytest.mark.django_db(transaction=True)
def test_msg_counts_end_bad(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&start=20200101&end=142'
     response = client.get(url)
     data = response.json()
     assert response.status_code == 400
     assert data == {'error': 'invalid end date'}


@pytest.mark.django_db(transaction=True)
def test_msg_counts_invalid_date(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&end=invalid'
     response = client.get(url)
     data = response.json()
     assert 'error' in data


@pytest.mark.django_db(transaction=True)
def test_msg_counts_duration_months(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&start=20130101&duration=1months'
     response = client.get(url)
     data = response.json()
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 1


@pytest.mark.django_db(transaction=True)
def test_msg_counts_duration_years(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&start=20130101&duration=1years'
     response = client.get(url)
     data = response.json()
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 3


@pytest.mark.django_db(transaction=True)
def test_msg_counts_duration_invalid(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&start=20130101&duration=1eon'
     response = client.get(url)
     data = response.json()
     assert response.status_code == 400
     assert data == {'error': 'invalid duration'}


@pytest.mark.django_db(transaction=True)
def test_subscriber_counts_one_list(client, subscribers):
     url = reverse('api_subscriber_counts') + '?list=pubone'
     response = client.get(url)
     data = response.json()
     print(data)
     print(vars(Subscriber.objects.first()))
     assert 'pubone' in data['subscriber_counts']
     assert data['subscriber_counts']['pubone'] == 5


@pytest.mark.django_db(transaction=True)
def test_subscriber_counts_no_lists(client, subscribers):
     url = reverse('api_subscriber_counts')
     response = client.get(url)
     data = response.json()
     print(data)
     print(vars(Subscriber.objects.first()))
     assert len(data['subscriber_counts']) == 2
     assert 'pubone' in data['subscriber_counts']
     assert data['subscriber_counts']['pubone'] == 5
     assert 'pubtwo' in data['subscriber_counts']
     assert data['subscriber_counts']['pubtwo'] == 3

@pytest.mark.django_db(transaction=True)
def test_subscriber_counts_date(client, subscribers):
     url = reverse('api_subscriber_counts') + '?list=pubtwo&date=2022-01-01'
     response = client.get(url)
     data = response.json()
     print(data)
     print(vars(Subscriber.objects.first()))
     assert 'pubtwo' in data['subscriber_counts']
     assert data['subscriber_counts']['pubtwo'] == 2

