import pytest
from django.urls import reverse


@pytest.mark.django_db(transaction=True)
def test_msg_counts_one_list(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone'
     response = client.get(url)
     data = response.json()
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 5


@pytest.mark.django_db(transaction=True)
def test_msg_counts_two_lists(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&list=pubtwo'
     response = client.get(url)
     data = response.json()
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 5
     assert 'pubtwo' in data['msg_counts']
     assert data['msg_counts']['pubtwo'] == 2


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
def test_msg_counts_end(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&end=20130601'
     response = client.get(url)
     data = response.json()
     assert 'end' in data
     assert data['end'] == '20130601'
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 3


@pytest.mark.django_db(transaction=True)
def test_msg_counts_invalid_date(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&end=invalid'
     response = client.get(url)
     data = response.json()
     assert 'error' in data


@pytest.mark.django_db(transaction=True)
def test_msg_counts_duration(client, messages):
     url = reverse('api_msg_counts') + '?list=pubone&1m'
     response = client.get(url)
     data = response.json()
     assert 'pubone' in data['msg_counts']
     assert data['msg_counts']['pubone'] == 5
