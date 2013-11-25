from django.conf import settings
from mlarchive import __date__, __rev__, __version__, __id__

from django.utils.log import getLogger
logger = getLogger('mlarchive.custom')

# --------------------------------------------------
# Context Processors
# --------------------------------------------------
def server_mode(request):
    'A context procesor that provides server_mode'
    return {'server_mode': settings.SERVER_MODE}

def revision_info(request):
    'A context processor that provides version and svn revision info'
    return {'revision_time': __date__[7:32],
            'revision_date': __date__[7:17],
            'revision_num': __rev__[6:-2],
            'revision_id': __id__[5:-2],
            'version_num': __version__ }
