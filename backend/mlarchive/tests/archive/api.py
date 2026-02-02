import base64
import datetime
import json
import pytest
import os
from datetime import timezone

from django.urls import reverse
from factories import EmailListFactory, MessageFactory
from mlarchive.archive.models import Subscriber, Message, EmailList
from mlarchive.blobdb.models import Blob
from mlarchive.archive.storage_utils import exists_in_storage


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
    date = datetime.datetime.now(timezone.utc).replace(second=0, microsecond=0)
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


@pytest.mark.django_db(transaction=True)
def test_subscriber_counts_not_exist(client, subscribers):
    url = reverse('api_subscriber_counts') + '?list=pubtwo&date=2001-01-01'
    response = client.get(url)
    assert response.status_code == 200
    assert response.json() == {}


def get_error_message(response):
    content = response.content.decode('utf-8')
    data_as_dict = json.loads(content)
    return data_as_dict['error']


@pytest.mark.django_db(transaction=True)
def test_import_message(client, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    url = reverse('api_import_message')
    settings.API_KEYS = {url: 'valid_token'}
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail.1')
    with open(path, 'rb') as f:
        message = f.read()
    message_b64 = base64.b64encode(message).decode()

    # no messages in incoming. Must us db query because name will be random
    assert not Blob.objects.filter(bucket='ml-messages-incoming').exists()

    # no api key
    response = client.post(
        url,
        {'list_name': 'apple', 'list_visibility': 'public', 'message': message_b64},
        headers={},
        content_type='application/json')
    assert response.status_code == 403

    # invalid api key
    response = client.post(
        url,
        {'list_name': 'apple', 'list_visibility': 'public', 'message': message_b64},
        headers={'X-API-Key': 'invalid_token'},
        content_type='application/json')
    assert response.status_code == 403

    # invalid visibility
    response = client.post(
        url,
        {'list_name': 'apple', 'list_visibility': 'opaque', 'message': message_b64},
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    assert response.status_code == 400

    # empty listname
    response = client.post(
        url,
        {'list_name': '', 'list_visibility': 'public', 'message': message_b64},
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    assert response.status_code == 400

    # valid request
    response = client.post(
        url,
        {'list_name': 'apple', 'list_visibility': 'public', 'message': message_b64},
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    assert response.status_code == 201

    # assert file exists in incoming
    assert Blob.objects.filter(
        bucket='ml-messages-incoming',
        name__startswith='apple.public',
    ).count() == 1

    blob = Blob.objects.filter(bucket='ml-messages-incoming').first()
    assert blob.content == message


@pytest.mark.django_db(transaction=True)
def test_import_message_private(client, settings):
    '''Ensure list_type variable is respected'''
    settings.CELERY_TASK_ALWAYS_EAGER = True
    url = reverse('api_import_message')
    settings.API_KEYS = {url: 'valid_token'}
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail.1')
    with open(path, 'rb') as f:
        message = f.read()
    message_b64 = base64.b64encode(message).decode()

    # pre-conditions
    assert Blob.objects.count() == 0

    # valid request
    response = client.post(
        url,
        {'list_name': 'apple', 'list_visibility': 'private', 'message': message_b64},
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    assert response.status_code == 201

    assert Blob.objects.filter(
        bucket='ml-messages-incoming',
        name__startswith='apple.private',
    ).count() == 1


@pytest.mark.django_db(transaction=True)
def test_import_message_integration(client, settings):
    '''Test end-to-end import, save and processing of message'''
    # skip sending task to broker and execute immediately
    settings.CELERY_TASK_ALWAYS_EAGER = True
    url = reverse('api_import_message')
    settings.API_KEYS = {url: 'valid_token'}
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', 'mail.1')
    with open(path, 'rb') as f:
        message = f.read()
    message_b64 = base64.b64encode(message).decode()

    # confirm pre-conditions
    assert Message.objects.count() == 0
    assert EmailList.objects.filter(name='apple').exists() is False
    # no messages in incoming. Must us db query because name will be random
    assert not Blob.objects.filter(bucket='ml-messages-incoming').exists()

    # valid request
    response = client.post(
        url,
        {'list_name': 'apple', 'list_visibility': 'public', 'message': message_b64},
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    assert response.status_code == 201

    # assert file exists in incoming
    assert Blob.objects.filter(
        bucket='ml-messages-incoming',
        name__startswith='apple.public',
    ).count() == 1

    blob = Blob.objects.filter(bucket='ml-messages-incoming').first()
    assert blob.content == message

    # assert list exists
    assert EmailList.objects.filter(name='apple', private=False).exists()

    # assert message exists, message-id
    msg = Message.objects.get(email_list__name='apple', msgid='0000000001@amsl.com')
    assert msg.subject == 'This is a test'

    # assert message blob exists in archive storage
    storage_blob_name = f'apple/{msg.hashcode.strip('=')}'
    assert exists_in_storage('ml-messages', storage_blob_name)
    assert exists_in_storage('ml-messages-json', storage_blob_name)


@pytest.mark.django_db(transaction=True)
def test_msg_search(client, search_api_messages, settings):
    # directly confirm messages in elasticsearch index
    from mlarchive.archive.backends.elasticsearch import ElasticsearchSimpleQuery
    esq = ElasticsearchSimpleQuery()
    s = esq.search
    print(s.count())
    response = s.execute()
    print(response)
    print(dir(response))
    print('indexed items: {}'.format(len(response.hits)))
    # ---------------------------------------
    url = reverse('api_search_message')
    settings.API_KEYS = {url: 'valid_token'}
    data = {
        'email_list': 'acme',
        'query': 'bananas'
    }
    # no token
    response = client.post(
        url,
        data=data,
        headers={},
        content_type='application/json')
    assert response.status_code == 403
    # invalid token
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'invalid_token'},
        content_type='application/json')
    assert response.status_code == 403
    # valid token
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    rdata = response.json()
    print(rdata)
    assert 'results' in rdata
    assert len(rdata['results']) == 2
    sorted_data = sorted(rdata['results'], key=lambda x: x['from'])
    assert sorted_data[0]['from'] == 'Bilbo Baggins <baggins@example.com>'
    assert sorted_data[0]['subject'] == 'This is a apples and bananas test'
    assert sorted_data[0]['content'].startswith('Hello')
    assert sorted_data[0]['message_id'] == 'api003'
    assert sorted_data[0]['url'].endswith('/arch/msg/acme/mWYjgi7riu4XN3F1uqlzSGVMAqM/')
    assert sorted_data[0]['date'] == '2020-03-01T17:54:55'
    # test limit
    data['limit'] = '1'
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    rdata = response.json()
    assert len(rdata['results']) == 1


@pytest.mark.django_db(transaction=True)
def test_msg_search_private(client, search_api_messages, settings):
    url = reverse('api_search_message')
    settings.API_KEYS = {url: 'valid_token'}
    acme = EmailList.objects.get(name='acme')
    acme.private = True
    acme.save()
    data = {
        'email_list': 'acme',
        'start_date': '2013-06-01',
        'query': 'subject:(bananas)'
    }
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    print(response.content)
    response_data = response.json()
    assert response.status_code == 400
    assert response_data == {'error': 'List not found: acme'}


@pytest.mark.django_db(transaction=True)
def test_msg_search_start_date(client, search_api_messages, settings):
    url = reverse('api_search_message')
    settings.API_KEYS = {url: 'valid_token'}
    data = {
        'email_list': 'acme',
        'start_date': '2013-06-01',
        'query': 'bananas'
    }
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    response_data = response.json()
    assert 'results' in response_data
    assert len(response_data['results']) == 2
    sorted_data = sorted(response_data['results'], key=lambda x: x['from'])
    assert sorted_data[0]['from'] == 'Bilbo Baggins <baggins@example.com>'
    # later
    data['start_date'] = '2020-02-01'
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    response_data = response.json()
    assert 'results' in response_data
    assert len(response_data['results']) == 1


@pytest.mark.django_db(transaction=True)
def test_msg_search_query(client, search_api_messages, settings):
    url = reverse('api_search_message')
    settings.API_KEYS = {url: 'valid_token'}
    # field query
    data = {
        'email_list': 'acme',
        'start_date': '2013-06-01',
        'query': 'subject:(bananas)'
    }
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    response_data = response.json()
    assert 'results' in response_data
    assert len(response_data['results']) == 2
    sorted_data = sorted(response_data['results'], key=lambda x: x['from'])
    assert sorted_data[0]['from'] == 'Bilbo Baggins <baggins@example.com>'
    # phrase match
    data['query'] = 'subject:("This-is-a-bananas-test")'
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    response_data = response.json()
    assert 'results' in response_data
    assert len(response_data['results']) == 1
    # phrase no match
    data['query'] = 'subject:("This-does-not-match-bananas-test")'
    response = client.post(
        url,
        data=data,
        headers={'X-API-Key': 'valid_token'},
        content_type='application/json')
    response_data = response.json()
    assert 'results' in response_data
    assert len(response_data['results']) == 0
