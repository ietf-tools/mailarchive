import unicodedata
from urllib import parse
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from django.conf import settings
from mlarchive.archive.models import MailmanMember, UserEmail
from mlarchive.archive.utils import get_known_emails

import logging
logger = logging.getLogger(__name__)


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


class CustomOIDCBackend(OIDCAuthenticationBackend):

    def create_user(self, claims):
        user = super().create_user(claims)
        # extra logic
        self.add_list_membership(user, claims)
        return user

    def update_user(self, user, claims):
        user = super().update_user(user, claims)
        # extra logic
        self.add_list_membership(user, claims)
        return user

    def add_list_membership(self, user, claims):
        '''Get all known emails for user from Datatracker. If they have a new email
        create UserEmail and add any EmailList.members relations as needed
        '''
        # get all emails from claims
        # not doing this initially, re-evaluate after new authenication system deployed
        # known_emails = claims.get('emails')
        try:
            known_emails = get_known_emails(user.email)
        except Exception as e:
            logger.error(f'get_known_emails failed ({e})')
            return
        new_emails = set(known_emails) - set(user.useremail_set.values_list('address', flat=True))
        for email in new_emails:
            UserEmail.objects.create(user=user, address=email)
            for member in MailmanMember.objects.filter(address=email):
                member.email_list.members.add(user)
