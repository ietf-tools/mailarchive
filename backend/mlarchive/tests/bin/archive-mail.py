import os
import pytest
from subprocess import Popen, PIPE, STDOUT

from django.conf import settings
from mlarchive.archive.models import Message


@pytest.mark.django_db(transaction=True)
def test_archive_mail_success(client):
    filename = 'mail.1'
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', filename)
    with open(path, 'rb') as f:
        data = f.read()
    print(type(data))
    # assert False
    # pass via stdin to archive script
    assert Message.objects.count() == 0
    path = os.path.join(settings.BASE_DIR, 'bin', 'archive-mail.py')
    command = [path, 'acme']
    proc = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate(data)
    assert Message.objects.count() == 1

