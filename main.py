import os
import pandas as pd
from playwright.sync_api import sync_playwright

# Path to the "links" folder
links_folder = "./links"

# Initialize a list to store all URLs
all_urls = []

# Google account credentials
google_email = r"email"
google_password = r"password"


# Function to process an Excel file
def process_excel_file(file_path):
    try:
        # Read the Excel file into a DataFrame
        df = pd.read_excel(file_path)

        # Check if the required columns exist
        if "Url" not in df.columns:
            print(f"File {file_path} does not contain the 'Url' column.")
            return

        # Extract the 'Url' column and add it to the global list
        urls = df["Url"].dropna().tolist()  # Drop any NaN values
        all_urls.extend(urls)

        print(f"Processed {file_path}. Found {len(urls)} URLs.")

    except Exception as e:
        print(f"Error processing {file_path}: {e}")


# Function to log in with Google using XPath selectors
def google_login(page):
    try:
        # Navigate to the login page
        page.goto("https://luatvietnam.vn/")  # Replace with the actual login URL

        # Click the "Login" button using the provided XPath
        page.click(
            '//span[contains(text(),"/ Đăng nhập")]'
        )  # XPath for the Login button

        # Wait for the Google login button to appear and click it
        page.wait_for_selector(
            '//form[@id="form0"]//a[@class="login-google social-cr google-login"]',
            timeout=20000,
        )
        page.click(
            '//form[@id="form0"]//a[@class="login-google social-cr google-login"]'
        )  # XPath for Google login button

        # Handle the popup (Google login page)
        with page.expect_popup() as popup_info:
            pass  # Popup is already opened by the previous click

        popup = popup_info.value
        popup.wait_for_load_state()

        # Interact with the Google login page
        popup.wait_for_selector(
            '//input[@id="identifierId"]', timeout=20000
        )  # Wait for the email input field
        popup.fill('//input[@id="identifierId"]', google_email)
        popup.press('//input[@id="identifierId"]', "Enter")

        popup.wait_for_selector(
            '//input[@name="Passwd"]', timeout=20000
        )  # Wait for the password input field
        popup.fill('//input[@name="Passwd"]', google_password)
        popup.press('//input[@name="Passwd"]', "Enter")

        # Wait for navigation to complete after login
        page.wait_for_selector(
            "a.dashboard-link", timeout=30000
        )  # Replace with a selector that confirms login success

        print("Google login successful!")

    except Exception as e:
        print(f"Google login failed: {e}")
        page.screenshot(path="debug.png")  # Take a screenshot for debugging
        exit()


# Function to process each URL after login
def process_url(page, url):
    try:
        # Navigate to the URL
        page.goto(url)

        # Perform actions on the page (e.g., scrape data, download files)
        # Example: Extract the page title
        title = page.title()
        print(f"URL: {url} | Title: {title}")

    except Exception as e:
        print(f"Error processing URL {url}: {e}")


# Main function to process all Excel files in the folder
def process_links_folder():
    # Loop through all files in the "links" folder
    for file_name in os.listdir(links_folder):
        # Check if the file matches the pattern Batch_[number].xlsx
        if file_name.startswith("Batch_") and file_name.endswith(".xlsx"):
            file_path = os.path.join(links_folder, file_name)
            process_excel_file(file_path)


# Run the script
with sync_playwright() as p:
    # Launch the browser
    browser = p.chromium.launch(
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
        ],
    )
    context = browser.new_context()
    page = context.new_page()

    try:
        # Log in with Google
        google_login(page)

        # Process all Excel files and collect URLs
        process_links_folder()

        # Process each collected URL
        for url in all_urls:
            process_url(page, url)

    finally:
        # Close the browser
        browser.close()

print("\nAll URLs processed.")
