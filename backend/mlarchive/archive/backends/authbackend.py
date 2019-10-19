from passlib.apache import HtpasswdFile
from django.conf import settings
from django.contrib.auth import get_user_model

User = get_user_model()

class HtauthBackend(object):
    def authenticate(self, request=None, username=None, password=None):
        passwd_file = getattr(settings, "HTAUTH_PASSWD_FILENAME", None)
        if passwd_file is None:
            return None

        ht = HtpasswdFile(passwd_file)
        if not ht.check_password(username, password):
            return None

        try:
            django_user = User.objects.get(username=username)
        except User.DoesNotExist:
            django_user = User.objects.create_user(username=username)
            django_user.is_staff = False
            django_user.save()

        return django_user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
