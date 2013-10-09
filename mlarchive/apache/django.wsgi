import os
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
path = os.path.abspath(base_dir + '/../..')

if not path in sys.path:
    sys.path.insert(0, path)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mlarchive.settings")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
