from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase

from mlarchive.archive.models import *

import mlarchive.archive.management.commands._classes as _classes
import os

# test utils.no_auth()
# test not logged in no private lists in results
# test logged in not auth lists

AUTH_USER='rcross'

class MainTest(TestCase):
    def test_main(self):
        "Main Test"
        url = reverse('archive')
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

    def test_browse(self):
        "Browse Test"
        url = reverse('archive_browse')
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

    def test_advsearch(self):
        "Advacned Search Test"
        url = reverse('archive_advsearch')
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)

    def test_admin(self):
        "Admin Test"
        url = reverse('archive_admin')
        response = self.client.get(url)
        self.assertEquals(response.status_code, 403)

        self.adminuser = User.objects.create_user('admin', 'admin@test.com', 'pass')
        self.adminuser.save()
        self.adminuser.is_staff = True
        self.adminuser.is_superuser = True
        self.adminuser.save()
        response = self.client.get(url,REMOTE_USER='admin')
        self.assertEquals(response.status_code, 200)

"""
self.assertTrue(os.path.exists(settings.IDSUBMIT_IDNITS_BINARY))
"""

class ModelsTest(TestCase):
    # fixtures = []
    path = os.path.join(settings.TEST_DATA_DIR,'test.mail')
    loader = _classes.Loader(path)

    def test_get_charset(self):
        msg = self.loader.mb[0]
        charset = get_charset(msg)
        self.failUnless(charset)
        self.assertEqual(charset,'us-ascii')

    #def test_handle_header(self):

    #loader.cleanup()

class LoadTest(TestCase):
    import mlarchive.archive.management.commands._classes as _classes

    #def test_get_date(self):
    #def test_get_subject(self):

class ParseQueryTest(TestCase):
    def testQueries(self):
        from mlarchive.archive.query_utils import parse
        queries = [('term','<SQ: AND content__contains=term>'),
                   ('-term','<SQ: AND NOT (content__contains=term)>'),
                   ('subject:term','<SQ: AND subject__contains=term>'),
                   ('-subject:term','<SQ: AND NOT (subject__contains=term)>'),
                   ('"term"','<SQ: AND content__exact=term >'),
                   ('"term1 term2"','<SQ: AND content__exact=term1 term2>'),
                   ('term1 term2','<SQ: AND (content__contains=term1 AND content__contains=term2)>'),
                   ('term1 AND term2','<SQ: AND (content__contains=term1 AND content__contains=term2)>'),
                   ('term1 OR term2','<SQ: OR (content__contains=term1 OR content__contains=term2)>'),
                   ('term1 NOT term2','<SQ: AND (content__contains=term1 AND NOT (content__contains=term2))>'),
                   #('term1-term2','<SQ: AND (content__contains=term1 AND content__contains=term2)>'),
                   ('term1-term2','<SQ: AND content__exact=term1 term2>'),
                   #('term1-term2-term3','<SQ: AND (content__contains=term1 AND content__contains=term2 AND content__contains=term3)>')]
                   ('term1-term2-term3','<SQ: AND content__exact=term1 term2 term3>')]
        for q in queries:
            self.assertEqual(repr(parse(q[0])),q[1])
"""
# skip tests against ietf database for now, the tables don't exist
class GetMembersTest(TestCase):
    def testSuccess(self):
        from ietf.person.models import Email, Person, User
        from mlarchive.bin.get_membership import lookup, process_members

        user = User.objects.using('ietf').create(username='jsmith@amsl.com')
        person = Person.objects.using('ietf').create(name='Joe Smith',ascii='Joe Smith',user=user)
        email = Email.objects.using('ietf').create(address='jsmith@amsl.com',person=person)
        self.assertEqual(lookup('jsmith@amsl.com'),'jsmith@amsl.com')
        person.user = None
        person.save()
        self.assertEqual(lookup('jsmith@amsl.com'),None)
        self.assertEqual(lookup('nobody@amsl.com'),None)
"""