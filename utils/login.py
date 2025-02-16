import os
import json
from datetime import datetime
from getpass import getpass


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
            print("Google login successful!")

        except Exception as wait_error:
            print("Debug info:")
            print(f"Current URL: {page.url}")
            print(f"Page title: {page.title()}")
            page.screenshot(path="login_failed.png")
            raise wait_error

    except Exception as e:
        print(f"Google login failed: {e}")
        page.screenshot(path="debug.png")
        exit()


def verify_login(page):
    """
    Verify if user is logged in by checking for user avatar
    Returns True if logged in, False otherwise
    """
    try:
        # Navigate to main page
        page.goto("https://luatvietnam.vn/", timeout=30000)

        # Try to find the user avatar which indicates successful login
        try:
            page.wait_for_selector(
                "//a[@title='Trang cá nhân']", timeout=10000, state="visible"
            )
            print("Login verified: User is logged in")
            return True

        except Exception:
            # Check alternative login indicators
            try:
                user_indicators = [
                    "//div[contains(@title, '@')]",
                    "//img[@class='avata-user']",
                ]

                for selector in user_indicators:
                    if page.locator(selector).is_visible(timeout=5000):
                        print("Login verified: User is logged in")
                        return True

            except Exception:
                print("Login verification failed: User is not logged in")
                return False

    except Exception as e:
        print(f"Error during login verification: {e}")
        return False


def save_cookies(context):
    cookies = context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump({"cookies": cookies, "timestamp": datetime.now().isoformat()}, f)
    print(f"Cookies saved to: {os.path.abspath(COOKIES_FILE)}")


def load_cookies(context):
    try:
        with open(COOKIES_FILE, "r") as f:
            data = json.load(f)
            context.add_cookies(data["cookies"])
            print("Previous session cookies loaded")
            return True
    except (FileNotFoundError, json.JSONDecodeError):
        print("No valid cookies found")
        return False


def check_credentials_exist():
    exists = os.path.exists(CREDENTIALS_FILE)
    if exists:
        print(f"Credentials file found at: {os.path.abspath(CREDENTIALS_FILE)}")
    else:
        print("No credentials file found. You will need to enter your credentials.")
    return exists


def save_credentials(email, password):
    credentials = {"email": email, "password": password}

    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(credentials, f)
    print(f"Credentials saved to: {os.path.abspath(CREDENTIALS_FILE)}")


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
        print("Please enter your Google credentials")
        email = input("Email: ")
        password = getpass("Password: ")
        save_credentials(email, password)

    return email, password
