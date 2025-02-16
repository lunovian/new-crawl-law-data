import os
from threading import Lock
from utils.login import (
    get_credentials,
    google_login,
    load_cookies,
    save_cookies,
    verify_login,
)
from utils.url_collector import UrlCollector
from utils.progress import ProgressTracker
from utils.download import DownloadManager
from utils.batch_processor import BatchProcessor
import pandas as pd
import argparse
from playwright.sync_api import sync_playwright  # type: ignore
from utils.signal_handler import ExitHandler
import logging
from utils.setup_logging import Logger


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


def first_setup(headless=True):
    """Setup initial login and save cookies if needed"""
    try:
        with sync_playwright() as playwright:
            # Browser arguments
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-setuid-sandbox",
                "--disable-extensions",
                "--window-size=1920,1080",
                "--start-maximized",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-web-security",
                "--allow-running-insecure-content",
            ]

            logging.info(
                f"[🌐] Starting browser in {'headless' if headless else 'visible'} mode"
            )

            browser = playwright.chromium.launch(
                headless=headless,
                args=browser_args,
                slow_mo=100 if not headless else 0,
            )

            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="Asia/Ho_Chi_Minh",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36",
                permissions=["geolocation"],
                ignore_https_errors=True,
                java_script_enabled=True,
                accept_downloads=True,
            )

            try:
                # Check existing cookies
                if load_cookies(context) and verify_login(context):
                    logging.info("[✓] Valid cookies found, login verified")
                    return True

                logging.warning(
                    "[⚠] No valid cookies found, starting new login process..."
                )
                page = context.new_page()

                # Set longer timeouts
                timeout = 120000 if not headless else 60000
                page.set_default_timeout(timeout)
                page.set_default_navigation_timeout(timeout)

                google_email, google_password = get_credentials()

                if not headless:
                    logging.info(
                        "[👀] Running in visible mode - please check browser window"
                    )

                page.goto("https://accounts.google.com", wait_until="networkidle")
                google_login(page, google_email, google_password)

                # Save cookies only after successful login
                if verify_login(context):
                    save_cookies(context)
                    logging.info("[✓] Login successful and cookies saved")
                    return True

                return False

            except Exception as e:
                logging.error(f"[✗] Login failed: {str(e)}")
                if headless:
                    logging.warning(
                        "[⚠] Headless mode failed, will retry in visible mode"
                    )
                    return False
                raise  # Re-raise if already in visible mode

            finally:
                if "page" in locals():
                    page.close()
                context.close()
                browser.close()

    except Exception as e:
        logging.error(f"[✗] Setup error: {str(e)}")
        return False


def main():
    # Setup logging first
    logger = Logger()
    logger.cleanup_old_logs()  # Clean logs older than 7 days
    logging.info("[🚀] Starting law data crawler...")

    # Parse command line arguments
    args = parse_args()
    headless = not args.no_headless

    # Initialize components
    exit_handler = ExitHandler()
    progress_tracker = ProgressTracker()
    batch_processor = BatchProcessor()
    safe_collector = ThreadSafeCollector()
    url_collector = UrlCollector()
    download_manager = DownloadManager()
    logging.info("[✓] Initialized components")

    # Register components with exit handler
    exit_handler.register_components(
        progress_tracker=progress_tracker,
        url_collector=url_collector,
        download_manager=download_manager,
    )

    # Share exit handler with components that need it
    url_collector.exit_handler = exit_handler
    download_manager.exit_handler = exit_handler

    # Improved login setup handling
    try:
        login_success = first_setup(headless)
        if not login_success:
            if headless:
                logging.warning("[⚠] Retrying in visible mode...")
                headless = False  # Switch to visible mode
                login_success = first_setup(headless)
                if not login_success:
                    logging.error("[✗] Setup failed in visible mode, exiting...")
                    return
            else:
                logging.error("[✗] Setup failed, exiting...")
                return
    except Exception as e:
        logging.error(f"[✗] Fatal setup error: {str(e)}")
        return

    # Log current mode after login
    logging.info(f"[🌐] Running in {'headless' if headless else 'visible'} mode")

    while True:
        logging.info("[⚡] Starting URL collection and download process...")

        # Process URLs (including retries for failed ones)
        try:
            url_collector.process_all_urls(
                batch_processor, safe_collector, headless, progress_tracker
            )
        except Exception as e:
            logging.error(f"[✗] Error during URL processing: {str(e)}")

        # Check final status
        df = pd.read_csv(progress_tracker.progress_file)
        failed_urls = len(df[df["url_status"] == progress_tracker.URL_STATUS_FAILED])
        pending_downloads = progress_tracker.get_pending_downloads()

        if not pending_downloads.empty:
            logging.info(
                f"[📥] Processing {len(pending_downloads)} pending downloads..."
            )
            download_manager.process_downloads(pending_downloads, progress_tracker)

        # Show final status
        logging.info("\n=== Final Status ===")
        logging.info(f"[{'✗' if failed_urls > 0 else '✓'}] Failed URLs: {failed_urls}")
        pending_count = len(progress_tracker.get_pending_downloads())
        logging.info(f"[📥] Pending Downloads: {pending_count}")

        if failed_urls == 0 and pending_count == 0:
            logging.info("[✓] All tasks completed successfully!")
            break

        retry = input("\nContinue processing? (y/n): ")
        if retry.lower() != "y":
            logging.info("[👋] Process terminated by user")
            break

    logging.info("[✓] Crawler finished")


if __name__ == "__main__":
    main()
