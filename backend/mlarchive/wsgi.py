import os
import sys
import syslog

path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if not path in sys.path:
    sys.path.insert(0, path)

# syslog.openlog("mailarchive", syslog.LOG_PID, syslog.LOG_USER)
# syslog.syslog("path: {}".format(sys.path) )
# syslog.syslog("version: {}".format(sys.version_info) )

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mlarchive.settings.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
