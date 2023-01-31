import unicodedata
from urllib import parse

from django.conf import settings


def generate_username(email):
    # Using Python 3 and Django 1.11+, usernames can contain alphanumeric
    # (ascii and unicode), _, @, +, . and - characters. So we normalize
    # it and slice at 150 characters.
    return unicodedata.normalize('NFKC', email)[:150]


def get_logout_url(request):
    hostname = request.get_host()
    redirect = parse.quote(f'https://{hostname}/arch/', safe='')
    token = request.session['oidc_id_token']
    endpoint = settings.OIDC_OP_X_END_SESSION_ENDPOINT
    url = f'{endpoint}?post_logout_redirect_uri={redirect}&id_token_hint={token}'
    return url
