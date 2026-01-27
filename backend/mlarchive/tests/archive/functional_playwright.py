import pytest
import re
from urllib.parse import urlparse, unquote
from playwright.sync_api import Page, expect

from django.urls import reverse

from mlarchive.archive.models import Message


@pytest.mark.django_db
class TestMyPlaywright:
    '''Playwright functional test cases'''

    # TEST MESSAGE VIEW NAVIGATIONS

    @pytest.mark.usefixtures("thread_messages")
    def test_message_detail_next_list(self, live_server, page: Page):
        '''Test next message in list button of message detail'''
        messages = Message.objects.all().order_by('date')
        url = f"{live_server.url}{messages[0].get_absolute_url()}"
        page.goto(url)

        page.locator('.next-in-list').first.click()

        # Take screenshot
        page.screenshot(path='tests/tmp/test_message_detail_next_list.png')

        # Assertions
        expect(page).to_have_title(messages[1].subject)
        expect(page.locator('body')).to_contain_text(messages[1].msgid)

    @pytest.mark.usefixtures("thread_messages")
    def test_message_detail_previous_list(self, live_server, page: Page):
        '''Test previous message in list button of message detail'''
        messages = Message.objects.all().order_by('date')
        assert len(messages) == 4
        url = f"{live_server.url}{messages[1].get_absolute_url()}"
        page.goto(url)

        page.locator('.previous-in-list').first.click()

        # Take screenshot
        page.screenshot(path='tests/tmp/test_message_detail_previous_list.png')

        # Assertions
        expect(page).to_have_title(messages[0].subject)
        expect(page.locator('body')).to_contain_text(messages[0].msgid)

    @pytest.mark.usefixtures("thread_messages")
    def test_message_detail_toggle_nav(self, live_server, page: Page):
        '''Test toggle navigation bar feature of message detail'''
        message = Message.objects.first()
        url = f"{live_server.url}{message.get_absolute_url()}"
        page.goto(url)

        # Take screenshot
        page.screenshot(path='tests/tmp/test_message_detail_toggle_nav.png')

        # navbar is there
        navbar = page.locator('.navbar-msg-detail').first
        expect(navbar).to_be_visible()

        # click hide
        page.get_by_text('Hide Navigation Bar').click()

        # navbar is gone
        expect(navbar).not_to_be_visible()

        # click to show
        page.get_by_text('Show Navigation Bar').click()

        # navbar is there
        expect(navbar).to_be_visible()

    @pytest.mark.usefixtures("thread_messages")
    def test_message_detail_toggle_msg_header(self, live_server, page: Page):
        '''Test toggle message header feature of message detail'''
        message = Message.objects.first()
        url = f"{live_server.url}{message.get_absolute_url()}"
        page.goto(url)

        # header is hidden
        header = page.locator('#msg-header')
        expect(header).not_to_be_visible()

        # click show
        page.get_by_text('Show header').click()

        # header is visible
        page.screenshot(path='tests/tmp/test_message_detail_toggle_msg_header.png')
        expect(header).to_be_visible()

        # click to hide
        page.get_by_text('Hide header').click()

        # header is hidden
        expect(header).not_to_be_visible()

    def test_back_to_search(self, live_server, page: Page):
        '''Test back to search button from search results'''
        url = f"{live_server.url}{reverse('archive')}"
        page.goto(url)

        # User performs search
        page.locator('#id_q').fill('data')
        page.locator('#id_q').press('Enter')

        # Get results page
        expect(page).to_have_title('IETF Mail List Archives Search Results')

        # Press back button
        page.locator('#modify-search').click()

        # End up back at basic search
        page.screenshot(path='tests/tmp/back_to_search.png')
        expect(page).to_have_title('IETF Mail List Archives')

    def test_back_to_advanced_search(self, live_server, page: Page):
        '''Test back to advanced search button from search results'''
        url = f"{live_server.url}{reverse('archive_advsearch')}"
        page.goto(url)

        # User performs search
        page.locator('#id_query-0-value').fill('data')
        page.locator('button[type="submit"]').click()

        # WAIT for the navigation to settle before grabbing the screenshot
        page.wait_for_url("**/arch/search/**")

        # Get results page
        page.screenshot(path='tests/tmp/back_to_advanced_search.png')
        expect(page).to_have_title('IETF Mail List Archives Search Results')

        # Press back button
        page.locator('#modify-search').click()

        # End up back at advanced search
        expect(page).to_have_title('Mail Archive Advanced Search')

    def test_advanced_search_contains(self, live_server, page: Page):
        '''Test advanced search with contains qualifier'''
        url = f"{live_server.url}{reverse('archive_advsearch')}"
        page.goto(url)

        page.locator('#id_query-0-value').fill('data')
        page.locator('button[type="submit"]').click()
        page.wait_for_url("**/arch/search/**")

        # Get results page
        expect(page).to_have_title('IETF Mail List Archives Search Results')
        page.screenshot(path='tests/tmp/advanced_search.png')

        o = urlparse(page.url)
        assert unquote(o.query) == 'qdr=a&start_date=&end_date=&email_list=&q=text:(data)&as=1'

    def test_advanced_search_exact(self, live_server, page: Page):
        '''Test advanced search with exact qualifier'''
        url = f"{live_server.url}{reverse('archive_advsearch')}"
        page.goto(url)

        # Select exact qualifier
        page.locator('#id_query-0-qualifier').select_option(label='exact')

        page.locator('#id_query-0-value').fill('data')
        page.locator('button[type="submit"]').click()
        page.wait_for_url("**/arch/search/**")

        # Get results page
        page.screenshot(path='tests/tmp/advanced_search_exact.png')
        expect(page).to_have_title('IETF Mail List Archives Search Results')

        o = urlparse(page.url)
        assert unquote(o.query) == 'qdr=a&start_date=&end_date=&email_list=&q=text:"data"&as=1'

    @pytest.mark.usefixtures("thread_messages")
    def test_message_detail_date_link(self, live_server, page: Page):
        '''Test date link navigation from message detail'''
        message = Message.objects.first()
        url = f"{live_server.url}{message.get_absolute_url()}"
        page.goto(url)

        # Toggle static mode
        page.locator('#nav-settings-anchor').click()
        page.locator('#toggle-static').click()

        # Click date link
        page.locator('.date-index').first.click()

        # Confirm index and message in focus
        expect(page).to_have_title(re.compile(r'.*Date Index.*'))

        # Check focused element
        focused_id = message.hashcode.strip('=')
        focused_element = page.locator(f'#{focused_id}')
        expect(focused_element).to_be_focused()


def force_login_playwright(user, page: Page, base_url: str):
    """
    Helper to force login a user by setting session cookie directly.
    Playwright version of the Selenium force_login helper.
    """
    from importlib import import_module
    from django.conf import settings
    from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY

    SessionStore = import_module(settings.SESSION_ENGINE).SessionStore
    selenium_login_start_page = getattr(settings, 'SELENIUM_LOGIN_START_PAGE', '/page_404/')

    # Navigate to a page first to set domain
    page.goto(f'{base_url}{selenium_login_start_page}')

    # Create session
    session = SessionStore()
    session[SESSION_KEY] = user.id
    session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()

    # Parse domain from base_url
    domain = base_url.split(':')[-2].split('/')[-1]

    # Add session cookie
    page.context.add_cookies([{
        'name': settings.SESSION_COOKIE_NAME,
        'value': session.session_key,
        'path': '/',
        'domain': domain,
    }])

    page.reload()


@pytest.mark.django_db
class TestAdminPlaywright:
    '''Admin Playwright functional test cases'''

    @pytest.mark.usefixtures("thread_messages", "admin_user")
    def test_admin_spam_mode(self, live_server, page: Page):
        '''Test Spam Mode of admin view'''
        from mlarchive.archive.models import EmailList
        from django.contrib.auth.models import User

        email_list = EmailList.objects.first()
        admin_url = reverse('archive_admin') + '?email_list=' + str(email_list.pk)
        url = f"{live_server.url}{admin_url}"

        user = User.objects.get(username='admin')
        force_login_playwright(user, page, live_server.url)

        page.goto(url)

        # spam tabs are hidden
        page.screenshot(path='tests/tmp/test_admin_spam_mode.png')
        nav_tabs = page.locator('.nav-tabs')
        expect(nav_tabs).not_to_be_visible()

        # Click spam toggle
        page.locator('#spam-toggle').click()

        # spam tabs displayed
        expect(nav_tabs).to_be_visible()
