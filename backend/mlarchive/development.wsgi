import os
import sys
import syslog

path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

syslog.openlog("mailarchive", syslog.LOG_PID, syslog.LOG_USER)

# Virtualenv support
virtualenv_activation = os.path.join(os.path.dirname(path), "env", "bin", "activate_this.py")
if os.path.exists(virtualenv_activation):
    syslog.syslog("Starting mailarchive wsgi with virtualenv %s" % os.path.dirname(os.path.dirname(virtualenv_activation)))
    exec(compile(open(virtualenv_activation, "rb").read(), virtualenv_activation, 'exec'), dict(__file__=virtualenv_activation))
else:
    syslog.syslog("Starting mailarchive wsgi without virtualenv")

if not path in sys.path:
    sys.path.insert(0, path)

syslog.syslog("path: {}".format(sys.path) )
syslog.syslog("version: {}".format(sys.version_info) )

os.environ['DJANGO_SETTINGS_MODULE'] = 'mlarchive.settings.development'

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
