import pytest

@pytest.mark.django_db(transaction=True)
def test_archive_mail_success(client):
    pass
