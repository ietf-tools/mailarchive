from mlarchive.archive.management.commands._classes import *

def test_get_base_subject():
    data = [('[ANCP] =?iso-8859-1?q?R=FCckruf=3A_Welcome_to_the_=22ANCP=22_mail?=\n\t=?iso-8859-1?q?ing_list?=',
             'R\xc3\xbcckruf: Welcome to the "ANCP" mailing list'),
            ('Re: [IAB] Presentation at IAB Tech Chat (fwd)','Presentation at IAB Tech Chat'),
            ('Re: [82companions] [Bulk]  Afternoon North Coast tour','Afternoon North Coast tour'),
            ('''[cdni-footprint] Fwd: Re: [CDNi] Rough Agenda for today's "CDNI Footprint/Capabilties Design Team Call"''','''Rough Agenda for today's "CDNI Footprint/Capabilties Design Team Call"'''),
            ('[dccp] [Fwd: Re: [Tsvwg] Fwd: WGLC for draft-ietf-dccp-quickstart-03.txt]','WGLC for draft-ietf-dccp-quickstart-03.txt'),
            ('[ANCP] Fw: note the boilerplate change','note the boilerplate change'),
            ('Re: [ANCP] RE: draft-ieft-ancp-framework-00.txt','draft-ieft-ancp-framework-00.txt')]

    for item in data:
        normal = normalize(item[0])
        base = get_base_subject(normal)
        assert base == item[1]
