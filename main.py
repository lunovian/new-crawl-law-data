import os
from threading import Lock
from utils.login import (
    get_credentials,
    google_login,
    load_cookies,
    save_cookies,
)
from utils.url_collector import UrlCollector
from utils.progress import ProgressTracker
from utils.download import process_downloads
from utils.batch_processor import BatchProcessor
import pandas as pd
import argparse
from playwright.sync_api import sync_playwright  # type: ignore
from utils.signal_handler import GracefulExitHandler


class ThreadSafeCollector:
    def __init__(self):
        self.lock = Lock()
        self.url_collector = UrlCollector()
        self.downloads = []

    def add_downloads(self, new_downloads):
        with self.lock:
            self.downloads.extend(new_downloads)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Law data crawler with configurable browser mode"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode (default: headless)",
    )
    return parser.parse_args()


def verify_and_setup_login(headless=True):
    """Setup initial login and save cookies if needed"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-setuid-sandbox",
                "--disable-extensions",
                "--window-size=1920,1080",
                "--start-maximized",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="Asia/Ho_Chi_Minh",
        )

        # Check if we have valid cookies
        if not load_cookies(context):
            print("\nNo valid cookies found. Performing initial login...")
            page = context.new_page()
            try:
                google_email, google_password = get_credentials()
                google_login(page, google_email, google_password)
                save_cookies(context)
                print("Login successful and cookies saved")
            finally:
                page.close()
        browser.close()


def main():
    args = parse_args()
    headless = not args.no_headless

    # Initialize components
    exit_handler = GracefulExitHandler()
    progress_tracker = ProgressTracker()
    batch_processor = BatchProcessor()
    safe_collector = ThreadSafeCollector()
    url_collector = UrlCollector()

    # Register components with exit handler
    exit_handler.register_components(
        progress_tracker=progress_tracker, url_collector=url_collector
    )

    # Handle login setup before starting main process
    verify_and_setup_login(headless)

    while True:
        print("\nStarting URL collection and download process...")
        # First check and process existing downloads
        if os.path.exists(progress_tracker.progress_file):
            pending_downloads = progress_tracker.get_pending_downloads()
            if not pending_downloads.empty:
                print(f"\nFound {len(pending_downloads)} pending downloads")
                process_downloads(pending_downloads, progress_tracker)

        print("\nProcessing URLs...")
        # Process URLs (including retries for failed ones)
        try:
            url_collector.process_all_urls(
                batch_processor, safe_collector, headless, progress_tracker
            )
        except Exception as e:
            print(f"\nError during URL processing: {str(e)}")

        # Check final status
        df = pd.read_csv(progress_tracker.progress_file)
        failed_urls = len(df[df["url_status"] == progress_tracker.URL_STATUS_FAILED])
        pending_downloads = len(progress_tracker.get_pending_downloads())

        print("\nFinal Status:")
        print(f"Failed URLs: {failed_urls}")
        print(f"Pending Downloads: {pending_downloads}")

        print("\nURLs processed and downloads completed!")

        if failed_urls == 0 and pending_downloads == 0:
            print("\nAll URLs processed and downloads completed!")
            break

        retry = input("\nContinue processing? (y/n): ")
        if retry.lower() != "y":
            break


if __name__ == "__main__":
    main()
