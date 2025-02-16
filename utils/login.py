import os
import json
from datetime import datetime
from getpass import getpass
import logging

COOKIES_FILE = "auth_cookies.json"
CREDENTIALS_FILE = "credentials.json"


# Function to log in with Google using XPath selectors
def google_login(page, google_email, google_password):
    try:
        page.goto("https://luatvietnam.vn/")
        page.click('//span[contains(text(),"/ Đăng nhập")]')

        page.wait_for_selector(
            '//form[@id="form0"]//a[@class="login-google social-cr google-login"]',
            timeout=20000,
        )
        page.click(
            '//form[@id="form0"]//a[@class="login-google social-cr google-login"]'
        )

        with page.expect_popup() as popup_info:
            popup = popup_info.value
            popup.wait_for_load_state()

            popup.wait_for_selector('//input[@id="identifierId"]', timeout=20000)
            popup.fill('//input[@id="identifierId"]', google_email)
            popup.press('//input[@id="identifierId"]', "Enter")

            popup.wait_for_selector('//input[@name="Passwd"]', timeout=20000)
            popup.fill('//input[@name="Passwd"]', google_password)
            popup.press('//input[@name="Passwd"]', "Enter")

        try:
            page.wait_for_selector(
                "//img[@class='avata-user']", timeout=45000, state="visible"
            )
            logging.info("Google login successful!")

        except Exception as wait_error:
            logging.debug("Debug info:")
            logging.debug(f"Current URL: {page.url}")
            logging.debug(f"Page title: {page.title()}")
            page.screenshot(path="login_failed.png")
            raise wait_error

    except Exception as e:
        logging.error(f"✗ Google login failed: {e}")
        page.screenshot(path="debug.png")


def verify_login(browser_obj):
    """Verify if user is logged in

    Args:
        browser_obj: Either Page or BrowserContext object

    Returns:
        bool: True if logged in, False otherwise
    """
    try:
        # Create new page if context was passed
        page_to_check = None
        needs_cleanup = False

        if hasattr(browser_obj, "new_page"):
            page_to_check = browser_obj.new_page()
            needs_cleanup = True
        else:
            page_to_check = browser_obj

        try:
            # Navigate to main page with timeout
            response = page_to_check.goto(
                "https://luatvietnam.vn/", timeout=60000, wait_until="networkidle"
            )

            if not response:
                logging.error("[✗] Failed to load verification page")
                return False

            # Check login status with multiple indicators
            selectors = [
                "//a[@title='Trang cá nhân']",
                "//div[contains(@title, '@')]",
                "//img[@class='avata-user']",
            ]

            for selector in selectors:
                try:
                    if page_to_check.locator(selector).is_visible(timeout=5000):
                        logging.info("[✓] Login verified: User is logged in")
                        return True
                except Exception:
                    continue

            logging.error("[✗] Login verification failed: User is not logged in")
            return False

        except Exception as e:
            logging.error(f"[✗] Error during page verification: {str(e)}")
            return False

        finally:
            if needs_cleanup and page_to_check:
                page_to_check.close()

    except Exception as e:
        logging.error(f"[✗] Error during login verification: {str(e)}")
        return False


def save_cookies(context):
    cookies = context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump({"cookies": cookies, "timestamp": datetime.now().isoformat()}, f)
    logging.info(f"Cookies saved to: {os.path.abspath(COOKIES_FILE)}")


def load_cookies(context):
    try:
        with open(COOKIES_FILE, "r") as f:
            data = json.load(f)
            context.add_cookies(data["cookies"])
            logging.info("Previous session cookies loaded")
            return True
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info("No valid cookies found")
        return False


def check_credentials_exist():
    exists = os.path.exists(CREDENTIALS_FILE)
    if exists:
        logging.info(f"Credentials file found at: {os.path.abspath(CREDENTIALS_FILE)}")
    else:
        logging.info(
            "No credentials file found. You will need to enter your credentials."
        )
    return exists


def save_credentials(email, password):
    credentials = {"email": email, "password": password}

    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(credentials, f)
    logging.info(f"Credentials saved to: {os.path.abspath(CREDENTIALS_FILE)}")


def load_credentials():
    try:
        with open(CREDENTIALS_FILE, "r") as f:
            credentials = json.load(f)
            return credentials.get("email"), credentials.get("password")
    except FileNotFoundError:
        return None, None


def get_credentials():
    check_credentials_exist()
    email, password = load_credentials()

    if not email or not password:
        logging.info("Please enter your Google credentials")
        email = input("Email: ")
        password = getpass("Password: ")
        save_credentials(email, password)

    return email, password
