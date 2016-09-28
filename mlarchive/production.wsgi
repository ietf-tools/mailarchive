import os
import sys

path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Virtualenv support
virtualenv_activation = os.path.join(path, "bin", "activate_this.py")
if os.path.exists(virtualenv_activation):
    execfile(virtualenv_activation, dict(__file__=virtualenv_activation))

if not path in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "mlarchive.settings.production"

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
