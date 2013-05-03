from django.conf import settings
from django.core.urlresolvers import reverse
from django.test import TestCase

from mlarchive.archive.models import *

import mlarchive.archive.management.commands._classes as _classes
import os

# test utils.no_auth()
# test not logged in no private lists in results
# test logged in not auth lists

SEC_USER='rcross'

class MainTest(TestCase):
    def test_main(self):
        "Main Test"
        url = reverse('archive')
        response = self.client.get(url)
        self.assertEquals(response.status_code, 200)
    
class ModelsTest(TestCase):
    # fixtures = []
    path = os.path.join(settings.TEST_DATA_DIR,'test.mail')
    loader = _classes.loader(path)
    
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