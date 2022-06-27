from django.conf import settings
from mlarchive import (__release_hash__, __release_branch__,
    __version__, __patch__)


# --------------------------------------------------
# Context Processors
# --------------------------------------------------


def server_mode(request):
    'A context procesor that provides server_mode'
    return {'server_mode': settings.SERVER_MODE}


def revision_info(request):
    'A context processor that provides version and release info'
    return {'release_hash': __release_hash__,
            'release_branch': __release_branch__,
            'version_num': __version__ + __patch__}


def static_mode_enabled(request):
    'A context procesor that provides static_mode_enabled'
    return {'static_mode_enabled': settings.STATIC_MODE_ENABLED}
