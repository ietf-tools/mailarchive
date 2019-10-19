import os
import pytest

from django.conf import settings


@pytest.mark.django_db(transaction=True)
def test_archive_mail_success(client):
    filename = 'mail.1'
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', filename)
    with open(path, 'rb') as f:
        data = f.read()
    print(type(data))
    assert False
    # pass via stdin to archive script
    command = ['archive-mail.py', 'acme']
    proc = Popen(
        command,
        stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate(data)

