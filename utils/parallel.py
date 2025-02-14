from playwright.async_api import async_playwright
from utils.login import google_login, load_cookies, save_cookies
import logging


class BrowserManager:
    def __init__(self, google_email, google_password, headless=False):
        self.google_email = google_email
        self.google_password = google_password
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def initialize(self):
        """Initialize single browser instance"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless, args=["--disable-dev-shm-usage"]
        )
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

        # Handle login
        if not await load_cookies(self.context):
            await google_login(self.page, self.google_email, self.google_password)
            await save_cookies(self.context)

        return self.page

    async def close(self):
        """Clean shutdown"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


# Remove all parallel processing functions
