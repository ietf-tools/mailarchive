import urlparse

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.urlresolvers import reverse
from selenium.webdriver.phantomjs.webdriver import WebDriver
from selenium.webdriver.support.wait import WebDriverWait

from mlarchive.archive.models import EmailList

timeout = 10

class MySeleniumTests(StaticLiveServerTestCase):

    @classmethod
    def setUpClass(cls):
        super(MySeleniumTests, cls).setUpClass()
        cls.selenium = WebDriver()
        cls.selenium.implicitly_wait(10)
        cls.selenium.set_window_size(1400,1000)

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super(MySeleniumTests, cls).tearDownClass()

    def test_back_to_search(self):
        # User performs search
        url = urlparse.urljoin(self.live_server_url, reverse('archive'))
        self.selenium.get(url)
        query_input = self.selenium.find_element_by_id('id_q')
        query_input.send_keys('data')
        self.selenium.find_element_by_name('search-form').submit();
        # Wait until the response is received
        WebDriverWait(self.selenium, timeout).until(
            lambda driver: driver.find_element_by_tag_name('body'))
        
        # Get results page
        self.assertIn('Search Results',self.selenium.title)
        self.selenium.get_screenshot_as_file('tests/tmp/mailarch_test.png')
        
        # Press back button
        self.selenium.find_element_by_id('modify-search').click();
        WebDriverWait(self.selenium, timeout).until(
            lambda driver: driver.find_element_by_tag_name('body'))
        
        # End up back at basic search
        self.assertEquals('Mail Archive',self.selenium.title)
        
    def test_back_to_advanced_search(self):
        # User performs search
        url = urlparse.urljoin(self.live_server_url, reverse('archive_advsearch'))
        self.selenium.get(url)
        query_input = self.selenium.find_element_by_id('id_query-0-value')
        query_input.send_keys('data')
        self.selenium.find_element_by_id('advanced-search-form').submit();
        # Wait until the response is received
        WebDriverWait(self.selenium, timeout).until(
            lambda driver: driver.find_element_by_tag_name('body'))
        
        # Get results page
        self.assertIn('Search Results',self.selenium.title)
        self.selenium.get_screenshot_as_file('tests/tmp/mailarch_test.png')
        
        # Press back button
        self.selenium.find_element_by_id('modify-search').click();
        WebDriverWait(self.selenium, timeout).until(
            lambda driver: driver.find_element_by_tag_name('body'))
        
        # End up back at advanced search
        self.assertEquals('Mail Archive Advanced Search',self.selenium.title)
        
    def test_back_to_browse(self):
        # Setup
        EmailList.objects.create(name='example')
        # User browses list
        url = urlparse.urljoin(self.live_server_url, reverse('archive_browse'))
        self.selenium.get(url)
        self.selenium.find_element_by_link_text('example').click()
        # Wait until the response is received
        WebDriverWait(self.selenium, timeout).until(
            lambda driver: driver.find_element_by_tag_name('body'))
        
        # Get results page
        self.assertIn('Search Results',self.selenium.title)
        self.selenium.get_screenshot_as_file('tests/tmp/mailarch_test.png')
        
        # Press back button
        self.selenium.find_element_by_id('modify-search').click();
        WebDriverWait(self.selenium, timeout).until(
            lambda driver: driver.find_element_by_tag_name('body'))
        
        # End up back at browse page
        self.assertEquals('Mail Archive Browse',self.selenium.title)