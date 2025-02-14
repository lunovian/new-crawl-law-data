import os
import json
from datetime import datetime
from getpass import getpass


COOKIES_FILE = "auth_cookies.json"
CREDENTIALS_FILE = "credentials.json"


# Function to log in with Google using XPath selectors
async def google_login(page, google_email, google_password):
    try:
        await page.goto("https://luatvietnam.vn/")
        await page.click('//span[contains(text(),"/ Đăng nhập")]')

        await page.wait_for_selector(
            '//form[@id="form0"]//a[@class="login-google social-cr google-login"]',
            timeout=20000,
        )
        await page.click(
            '//form[@id="form0"]//a[@class="login-google social-cr google-login"]'
        )

        async with page.expect_popup() as popup_info:
            popup = await popup_info.value
            await popup.wait_for_load_state()

            await popup.wait_for_selector('//input[@id="identifierId"]', timeout=20000)
            await popup.fill('//input[@id="identifierId"]', google_email)
            await popup.press('//input[@id="identifierId"]', "Enter")

            await popup.wait_for_selector('//input[@name="Passwd"]', timeout=20000)
            await popup.fill('//input[@name="Passwd"]', google_password)
            await popup.press('//input[@name="Passwd"]', "Enter")

        try:
            await page.wait_for_selector(
                "//img[@class='avata-user']", timeout=45000, state="visible"
            )
            print("Google login successful!")

        except Exception as wait_error:
            print("Debug info:")
            print(f"Current URL: {await page.url}")
            print(f"Page title: {await page.title()}")
            await page.screenshot(path="login_failed.png")
            raise wait_error

    except Exception as e:
        print(f"Google login failed: {e}")
        await page.screenshot(path="debug.png")
        exit()


async def save_cookies(context):
    cookies = await context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump({"cookies": cookies, "timestamp": datetime.now().isoformat()}, f)
    print(f"Cookies saved to: {os.path.abspath(COOKIES_FILE)}")


async def load_cookies(context):
    try:
        with open(COOKIES_FILE, "r") as f:
            data = json.load(f)
            await context.add_cookies(data["cookies"])
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
