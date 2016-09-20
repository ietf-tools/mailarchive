from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium.webdriver.phantomjs.webdriver import WebDriver
from selenium.webdriver.support.wait import WebDriverWait

timeout = 10

class MySeleniumTests(StaticLiveServerTestCase):

    @classmethod
    def setUpClass(cls):
        super(MySeleniumTests, cls).setUpClass()
        cls.selenium = WebDriver()
        cls.selenium.implicitly_wait(10)

    @classmethod
    def tearDownClass(cls):
        cls.selenium.quit()
        super(MySeleniumTests, cls).tearDownClass()

    def test_back_to_search(self):
        # User searches for term 'data'
        self.selenium.get('%s%s' % (self.live_server_url, '/arch/'))
        query_input = self.selenium.find_element_by_id('id_q')
        query_input.send_keys('data')
        self.selenium.find_element_by_name('search-form').submit();
        # Wait until the response is received
        WebDriverWait(self.selenium, timeout).until(
            lambda driver: driver.find_element_by_tag_name('body'))
        
        # Get results page
        self.assertIn('Search Results',self.selenium.title)
        self.selenium.get_screenshot_as_file('/a/home/rcross/web/test/mailarch_test.png')
        
        # Press back button
        self.selenium.find_element_by_id('modify-search').click();
        WebDriverWait(self.selenium, timeout).until(
            lambda driver: driver.find_element_by_tag_name('body'))
        
        # End up back at basic search
        self.assertEquals('Mail Archive',self.selenium.title)
        
    def test_back_to_advanced_search(self):
        pass
        
    def test_back_to_browse(self):
        pass
        