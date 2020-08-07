'''
Broilerplate for standalone Django scripts
'''
import os
import sys

#DEFAULT_DJANGO_SETTINGS_MODULE = 'mlarchive.settings.production'
DEFAULT_DJANGO_SETTINGS_MODULE = 'mlarchive.settings.settings'


def do_setup(django_settings=None):
    '''Boilerplate environment setup for bin scripts'''
    path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if django_settings:
        pass
    elif 'DJANGO_SETTINGS_MODULE' in os.environ:
        django_settings = os.environ['DJANGO_SETTINGS_MODULE']
    else:
        django_settings = DEFAULT_DJANGO_SETTINGS_MODULE

    if not path in sys.path:
        sys.path.insert(0, path)

    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', django_settings)
    django.setup()

    from django.conf import settings
    # print settings.SERVER_MODE
    # print settings.DEBUG
    # print settings.HAYSTACK_SIGNAL_PROCESSOR
