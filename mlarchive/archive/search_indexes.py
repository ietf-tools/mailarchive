from mlarchive.utils.test_utils import get_search_backend
if get_search_backend() == 'xapian':
    from mlarchive.archive.indexes import XapianMessageIndex as MessageIndex
else:
    from mlarchive.archive.indexes import ElasticMessageIndex as MessageIndex  # noqa


