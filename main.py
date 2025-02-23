import os
from threading import Lock
import traceback
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
        description="Law data crawler with configurable modes"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode (default: headless)",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only collect URLs without downloading",
    )
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Only process pending downloads without collecting",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Page load timeout in seconds (default: 120)",
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

            try:
                browser_pid = browser.subprocess_pid
                if browser_pid and "exit_handler" in globals():
                    exit_handler.register_browser_process(browser_pid)
                    logging.debug(f"[⚙] Registered setup browser PID: {browser_pid}")
            except Exception as e:
                logging.warning(f"[⚠] Could not register browser PID: {e}")

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

    # Verify batches directory and files
    success, batches_dir = _verify_batches_dir()
    if not success:
        return

    # Parse command line arguments
    args = parse_args()
    headless = not args.no_headless
    collect_only = args.collect_only
    download_only = args.download_only

    if collect_only and download_only:
        logging.error("[✗] Cannot use --collect-only and --download-only together")
        return

    try:
        # Initialize components
        global exit_handler
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

        # Share exit handler with components
        url_collector.exit_handler = exit_handler
        download_manager.exit_handler = exit_handler

    except Exception as e:
        logging.error(f"[✗] Component initialization failed: {str(e)}")
        return

    # Only perform login if we need to collect URLs
    if not download_only:
        logging.info("[🔍] Starting URL collection...")
        try:
            login_success = first_setup(headless)
            if not login_success:
                if headless:
                    logging.warning("[⚠] Retrying in visible mode...")
                    headless = False
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

        logging.info(f"[🌐] Running in {'headless' if headless else 'visible'} mode")

    try:
        # URL Collection Phase
        if not download_only:
            logging.info("[🔍] Starting URL collection...")
            try:
                # Update validate_urls function:
                def validate_urls(urls_df):
                    """Validate and clean URL data"""
                    if urls_df.empty:
                        return urls_df

                    # Remove duplicates
                    urls_df = urls_df.drop_duplicates(subset=["url"])

                    # Ensure URL format
                    urls_df["url"] = urls_df["url"].astype(str)
                    urls_df = urls_df[
                        urls_df["url"].str.contains("http", case=False, na=False)
                    ]

                    # Ensure single values in cells
                    for col in urls_df.columns:
                        urls_df[col] = urls_df[col].apply(
                            lambda x: x[0] if isinstance(x, (list, tuple)) else x
                        )
                    return urls_df

                url_collector.process_all_urls(
                    batch_processor,
                    safe_collector,
                    headless,
                    progress_tracker,
                    validate_urls,
                )
            except Exception as e:
                logging.error(f"[✗] Error during URL processing: {str(e)}")
                logging.debug(f"Traceback: {traceback.format_exc()}")

                if not collect_only:  # Continue to downloads if not collect-only
                    logging.warning(
                        "[⚠] Continuing to download phase despite collection errors"
                    )
                else:
                    raise

        # Download Phase
        if not collect_only:
            logging.info("[📥] Checking for pending downloads...")
            pending_downloads = progress_tracker.get_pending_downloads()

            if pending_downloads.empty:
                logging.info("[✓] No pending downloads found")
            else:
                total_downloads = len(pending_downloads)
                logging.info(f"[📥] Found {total_downloads} pending downloads")
                download_manager.process_downloads(pending_downloads, progress_tracker)

        # Final Status Report
        if os.path.exists(progress_tracker.progress_file):
            df = pd.read_csv(progress_tracker.progress_file)
            failed_urls = len(
                df[df["url_status"] == progress_tracker.URL_STATUS_FAILED]
            )
            pending_count = len(progress_tracker.get_pending_downloads())

            logging.info("\n=== Final Status ===")
            if not download_only:
                logging.info(
                    f"[{'✗' if failed_urls > 0 else '✓'}] Failed URLs: {failed_urls}"
                )
            if not collect_only:
                logging.info(f"[📥] Remaining Downloads: {pending_count}")

            # Ask for retry only in full process mode
            if not (collect_only or download_only) and (
                failed_urls > 0 or pending_count > 0
            ):
                retry = input("\nContinue processing? (y/n): ")
                if retry.lower() == "y":
                    if "exit_handler" in locals():
                        exit_handler.cleanup()  # Clean up before restart
                    main()  # Restart the process
                    return

    except KeyboardInterrupt:
        logging.info("\n[⚠] Process interrupted by user")
        if "exit_handler" in locals():
            exit_handler.cleanup()

    except Exception as e:
        logging.error(f"[✗] Fatal error: {str(e)}")
        if "exit_handler" in locals():
            exit_handler.cleanup()

    finally:
        logging.info("[✓] Crawler finished")
        # Final terminal restoration attempt
        if "exit_handler" in locals():
            exit_handler.restore_terminal()


if __name__ == "__main__":
    main()
