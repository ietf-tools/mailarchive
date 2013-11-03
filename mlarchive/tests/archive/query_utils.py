from mlarchive.archive.query_utils import *

def test_parse():
    queries = [(u'term','<SQ: AND content__contains=term>'),
               (u'-term','<SQ: AND NOT (content__contains=term)>'),
               (u'subject:term','<SQ: AND subject__contains=term>'),
               (u'-subject:term','<SQ: AND NOT (subject__contains=term)>'),
               (u'"term"','<SQ: AND content__exact=term >'),
               (u'"term1 term2"','<SQ: AND content__exact=term1 term2>'),
               (u'term1 term2','<SQ: AND (content__contains=term1 AND content__contains=term2)>'),
               (u'term1 AND term2','<SQ: AND (content__contains=term1 AND content__contains=term2)>'),
               (u'term1 OR term2','<SQ: OR (content__contains=term1 OR content__contains=term2)>'),
               (u'term1 NOT term2','<SQ: AND (content__contains=term1 AND NOT (content__contains=term2))>'),
               (u'term1-term2','<SQ: AND content__exact=term1 term2>'),
               (u'term1-term2-term3','<SQ: AND content__exact=term1 term2 term3>')]
    for q,r in queries:
        assert repr(parse(q)) == r