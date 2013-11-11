from django.conf import settings
from django.contrib.auth.models import User, UNUSABLE_PASSWORD

from htauth.htpasswd import check_password, NoSuchUser

class HtauthBackend(object):
    supports_inactive_user = False

    def authenticate(self, username=None, password=None):
        password_file = settings.HTAUTH_PASSWD_FILENAME
        try:
            login_valid = check_password(username, password, password_file)
        except NoSuchUser:
            return None
        if not login_valid:
            return None

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # Create a new user. Note that we can set password
            # to anything, because it won't be checked; the password
            # from settings.py will.
            user = User(username=username, password=UNUSABLE_PASSWORD)
            #user.is_staff = True
            #user.is_superuser = True
            user.save()
        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
