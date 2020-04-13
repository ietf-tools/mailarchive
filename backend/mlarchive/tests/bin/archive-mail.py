import os
import pytest
import time
from subprocess import Popen, PIPE, STDOUT

from django.conf import settings
from mlarchive.archive.models import Message, EmailList


"""
@pytest.mark.django_db(transaction=True)
def test_archive_mail_success(client):
    filename = 'mail.1'
    path = os.path.join(settings.BASE_DIR, 'tests', 'data', filename)
    #with open(path, 'rb') as f:
    #    data = f.read()
    f = open(path, 'rb')
    # print(type(data))
    # assert False
    # pass via stdin to archive script
    assert Message.objects.count() == 0
    path = os.path.join(settings.BASE_DIR, 'bin', 'archive-mail.py')
    assert os.path.isfile(path)
    command = ['/bin/bash', '-c', path, 'acme']
    # command = str(path) + ' acme'
    proc = Popen(command,
        stdin=f,
        stdout=PIPE,
        stderr=PIPE,
        # shell=True,
        cwd=os.path.dirname(path),
        env={'DJANGO_SETTINGS_MODULE':'mlarchive.settings.test'})
    # stdout, stderr = proc.communicate(input=data)
    # print(stdout, stderr, proc.returncode)
    returncode = proc.wait()
    print(returncode,proc.stderr.read(),proc.stdout.read())
    # print(data)
    time.sleep(5)
    assert EmailList.objects.get(name='acme')
    assert Message.objects.count() == 1
"""
