from mlarchive.utils.encoding import decode_rfc2047_header

def test_decode_rfc2047_header():
    data = [('=?utf-8?b?562U5aSNOiAgQU5DUCBGcmFtZXdvcmsgdXBkYXRl?=',
            u'\u7b54\u590d:  ANCP Framework update'),
            ('To: =?iso-8859-1?Q?Ivan_Skytte_J=F8rgensen?= <isj@i1.dk>',
            u'To:  Ivan Skytte J\xf8rgensen  <isj@i1.dk>'),
            ('nothing to convert',u'nothing to convert')]
    for item in data:
        assert decode_rfc2047_header(item[0]) == item[1]
