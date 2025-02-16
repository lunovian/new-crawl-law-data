import csv
import os
from datetime import datetime
from bs4 import BeautifulSoup
import re
from playwright.async_api import Error as TimeoutError
from playwright.sync_api import sync_playwright  # type: ignore
from utils.batch_processor import BatchProcessor
from utils.download import DownloadManager
from utils.progress import ProgressTracker
from utils.signal_handler import ExitHandler
import logging
from utils.login import (
    get_credentials,
    load_cookies,
)
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
import math


class UrlCollector:
    def __init__(self, urls_file="download_urls.csv"):
        self.urls_file = urls_file
        self._init_file()
        self.timeout = 30000
        self.max_retries = 3
        self.progress_threshold = 100
        self.processed_count = 0
        self.download_manager = DownloadManager()
        self.progress_tracker = ProgressTracker()
        self.exit_handler = ExitHandler()

        # URL collection threads (more conservative)
        self.url_threads = min(cpu_count() - 1, 8)  # Cap at 4
        self.url_threads = max(2, self.url_threads)  # Minimum 2

        # Path to the "batches" folder
        self.links_folder = "./batches"

        # Initialize a list to store all URLs
        self.saved_urls = []

        # Get Google account credentials
        self.google_email, self.google_password = get_credentials()

    def _init_file(self):
        """Initialize download_urls.csv if it doesn't exist"""
        if not os.path.exists(self.urls_file):
            with open(self.urls_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["timestamp", "page_url", "doc_url", "pdf_url", "status"]
                )

    def get_processed_urls(self):
        """Get set of already processed URLs from download_urls.csv"""
        if os.path.exists(self.urls_file):
            df = pd.read_csv(self.urls_file)
            return set(df["page_url"].values)
        return set()

    def _update_progress(self, url, status):
        """Update progress with threshold-based printing"""
        self.processed_count += 1
        if self.processed_count % self.progress_threshold == 0:
            logging.info(f"[✓] Processed {self.processed_count} URLs")
            logging.info(f"[📥] Last URL: {url}")
            logging.info(f"[📥] Status: {status}")

    def collect_urls(self, page, url):
        """Collect document and PDF URLs from a page"""
        processed_urls = self.get_processed_urls()
        if url in processed_urls:
            self.progress_tracker.update_progress(url, "SKIPPED")
            return "", ""

        for attempt in range(self.max_retries):
            try:
                # Set timeouts
                page.set_default_timeout(60000)
                page.set_default_navigation_timeout(60000)

                # Block unwanted resources
                page.route(
                    "**/*.{png,jpg,jpeg,gif,css,woff,woff2}",
                    lambda route: route.abort(),
                )

                try:
                    # Navigate with better error handling
                    logging.info(f"[🌐] Attempt {attempt + 1}: Loading {url}")
                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",  # Changed from networkidle
                        timeout=120000,
                    )

                    if not response:
                        raise Exception("No response received")

                    if not response.ok:
                        raise Exception(
                            f"HTTP {response.status}: {response.status_text}"
                        )

                    # Wait for network to be idle after load
                    try:
                        page.wait_for_load_state("networkidle", timeout=30000)
                    except TimeoutError:
                        logging.warning(
                            f"[⚠] Network idle timeout on {url}, continuing anyway"
                        )

                    # Get page content and parse
                    html_content = page.content()
                    if not html_content:
                        raise Exception("Empty page content")

                    soup = BeautifulSoup(html_content, "html.parser")

                    # Find links with better logging
                    static_links = {"doc": "", "pdf": ""}
                    found_links = soup.find_all(
                        "a", href=re.compile(r"static\.luatvietnam\.vn")
                    )

                    if not found_links:
                        logging.warning(f"[⚠] No static links found on {url}")

                    for link in found_links:
                        href = link["href"].lower()
                        if href.endswith(".pdf"):
                            static_links["pdf"] = href
                            logging.debug(f"[📄] Found PDF: {href}")
                        elif any(href.endswith(ext) for ext in [".doc", ".docx"]):
                            static_links["doc"] = href
                            logging.debug(f"[📄] Found DOC: {href}")
                        if static_links["doc"] and static_links["pdf"]:
                            break

                    # Save results with explicit status
                    url_status = (
                        "FOUND"
                        if (static_links["doc"] or static_links["pdf"])
                        else "FAILED"
                    )
                    logging.info(
                        f"[{'✓' if url_status == 'FOUND' else '✗'}] {url}: {url_status}"
                    )

                    self.save_urls(
                        page_url=url,
                        doc_url=static_links["doc"],
                        pdf_url=static_links["pdf"],
                        url_status=url_status,
                        download_status="NOT_STARTED",
                    )

                    self.progress_tracker.update_progress(
                        url=url,
                        status=url_status,
                        doc_url=static_links["doc"],
                        pdf_url=static_links["pdf"],
                    )
                    self._update_progress(url, url_status)
                    return static_links["doc"], static_links["pdf"]

                except TimeoutError as te:
                    logging.error(
                        f"[✗] Timeout on attempt {attempt + 1} for {url}: {str(te)}"
                    )
                    if attempt == self.max_retries - 1:
                        self.save_urls(page_url=url, url_status="FAILED")
                    continue

                except Exception as e:
                    logging.error(
                        f"[✗] Error on attempt {attempt + 1} for {url}: {str(e)}"
                    )
                    if attempt == self.max_retries - 1:
                        self.save_urls(page_url=url, url_status="FAILED")
                    continue

            except Exception as e:
                logging.error(
                    f"[✗] Fatal error on attempt {attempt + 1} for {url}: {str(e)}"
                )
                if attempt == self.max_retries - 1:
                    self.save_urls(page_url=url, url_status="FAILED")

        return "", ""

    def save_urls(
        self,
        page_url,
        doc_url="",
        pdf_url="",
        url_status="",
        download_status="NOT_STARTED",
    ):
        """Save URLs to CSV file with status tracking

        Args:
            page_url (str): Original page URL
            doc_url (str, optional): DOC file URL. Defaults to "".
            pdf_url (str, optional): PDF file URL. Defaults to "".
            url_status (str, optional): URL processing status. Defaults to "".
            download_status (str, optional): Download status. Defaults to "NOT_STARTED".
        """
        with open(self.urls_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    page_url,
                    doc_url,
                    pdf_url,
                    url_status,
                    download_status,
                ]
            )

    def process_url_batch(
        self, urls, google_email, google_password, collector, headless=True
    ):
        """Process a batch of URLs with a single browser instance
        Args:
            urls (list): List of URLs to process
            google_email (str): Google account email
            google_password (str): Google account password
            collector (dict): Collector methods
            headless (bool): Whether to run browser in headless mode
        """
        results = []

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

            if hasattr(self, "exit_handler"):
                browser_pid = browser.subprocess_pid
                self.exit_handler.register_browser_process(browser_pid)
                logging.debug(f"[⚙] Registered collector browser PID: {browser_pid}")

            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="Asia/Ho_Chi_Minh",
            )

            page = context.new_page()

            try:
                # Handle login
                if not load_cookies(context):
                    raise Exception("No valid cookies found. Please run setup first.")

                # Process each URL
                for url in urls:
                    retry_count = 0
                    success = False

                    while retry_count < self.max_retries and not success:
                        try:
                            page = context.new_page()
                            doc_url, pdf_url = self.collect_urls(page, url)

                            if doc_url or pdf_url:
                                try:
                                    # Add to shared collector's downloads
                                    downloads = []
                                    if doc_url:
                                        downloads.append(
                                            {
                                                "page_url": url,
                                                "url": doc_url,
                                                "type": "doc",
                                            }
                                        )
                                    if pdf_url:
                                        downloads.append(
                                            {
                                                "page_url": url,
                                                "url": pdf_url,
                                                "type": "pdf",
                                            }
                                        )
                                    collector.add_downloads(downloads)
                                    success = True
                                except Exception as e:
                                    logging.error(f"✗ Failed: {e}")

                            # Store result regardless of success
                            results.append((url, doc_url, pdf_url))
                            break

                        except Exception as e:
                            logging.error(
                                f"Attempt {retry_count + 1} failed for URL {url}: {e}"
                            )
                            retry_count += 1
                        finally:
                            if "page" in locals():
                                page.close()

                return results

            finally:
                browser.close()
                logging.info(
                    f"Batch processing completed. Total URLs processed: {self.processed_count}"
                )

    def load_pending_downloads(self):
        """Load URLs that need to be downloaded"""
        downloads = []
        if os.path.exists(self.urls_file):
            with open(self.urls_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["status"] == "FOUND":
                        if row["doc_url"]:
                            downloads.append(
                                {
                                    "page_url": row["page_url"],
                                    "url": row["doc_url"],
                                    "type": "doc",
                                }
                            )
                        if row["pdf_url"]:
                            downloads.append(
                                {
                                    "page_url": row["page_url"],
                                    "url": row["pdf_url"],
                                    "type": "pdf",
                                }
                            )
        return downloads

    def process_url_collection(
        self, batch_processor, safe_collector, headless, progress_tracker
    ):
        """Process URL collection and new downloads"""
        try:
            # Register components with exit handler
            self.exit_handler.progress_tracker = progress_tracker
            self.exit_handler.url_collector = self
            self.exit_handler.register_components(
                download_manager=self.download_manager
            )

            # Process Excel files and get unprocessed URLs
            saved_urls = batch_processor.process_folder("batches")
            if not saved_urls:
                logging.info("No URLs found in batch files!")
                return

            unprocessed_urls = progress_tracker.filter_unprocessed_urls(saved_urls)
            if not unprocessed_urls:
                logging.info("No new URLs to process!")
                return

            # Set total URLs for progress tracking
            progress_tracker.set_total_urls(len(unprocessed_urls))
            logging.info(f"Processing {len(unprocessed_urls)} URLs...")

            # Calculate batch size and create batches
            try:
                batch_size = math.ceil(len(unprocessed_urls) / self.url_threads)
                url_batches = [
                    unprocessed_urls[i : i + batch_size]
                    for i in range(0, len(unprocessed_urls), batch_size)
                ]
            except Exception as e:
                logging.error(f"Error creating URL batches: {e}")
                return

            # Print thread and batch information
            logging.info(f"System CPU count: {cpu_count()}")
            logging.info(f"Using {self.url_threads} threads")
            logging.info(f"Batch size: {batch_size} URLs per thread")

            # Prepare arguments for each thread - remove headless from args
            thread_args = [
                (
                    batch,  # urls
                    self.google_email,  # email
                    self.google_password,  # password
                    safe_collector.url_collector,  # collector_methods
                    headless,  # Add headless parameter
                )
                for batch in url_batches
            ]

            logging.info("Starting URL collection...")
            # Process URL batches in parallel using threads
            with ThreadPoolExecutor(max_workers=self.url_threads) as executor:
                self.exit_handler.register_executor(executor)
                futures = []
                thread_map = {}  # Store batch URLs for error handling

                try:
                    # Update thread submission to include headless
                    for thread_arg in thread_args:
                        if self.exit_handler.exit_requested:
                            logging.info("[⚠] Exit requested, stopping new submissions")
                            break

                        try:
                            urls, email, password, url_collector, is_headless = (
                                thread_arg
                            )
                            future = executor.submit(
                                url_collector.process_url_batch,
                                urls,
                                email,
                                password,
                                safe_collector,
                                is_headless,
                            )
                            thread_map[future] = urls
                            futures.append(future)
                        except Exception as e:
                            logging.error(f"Error submitting batch to thread pool: {e}")
                            continue

                    # Process results as they complete
                    for future in futures:
                        if self.exit_handler.exit_requested:
                            logging.info(
                                "[⚠] Exit requested, processing remaining results"
                            )
                            break

                        try:
                            result = future.result(
                                timeout=300
                            )  # 5 minute timeout per batch
                            if result:
                                for url, doc_url, pdf_url in result:
                                    try:
                                        if doc_url or pdf_url:
                                            progress_tracker.update_url_status(
                                                url,
                                                doc_url=doc_url,
                                                pdf_url=pdf_url,
                                                status=progress_tracker.URL_STATUS_FOUND,
                                            )
                                        else:
                                            progress_tracker.update_url_status(
                                                url,
                                                status=progress_tracker.URL_STATUS_FAILED,
                                            )
                                        progress_tracker.update_progress()
                                    except Exception as e:
                                        logging.error(
                                            f"Error updating progress for URL {url}: {e}"
                                        )
                                        continue

                        except TimeoutError:
                            logging.error("[✗] Batch processing timed out")
                            failed_urls = thread_map[future]
                            for failed_url in failed_urls:
                                progress_tracker.update_url_status(
                                    failed_url,
                                    status=progress_tracker.URL_STATUS_FAILED,
                                )
                        except Exception as e:
                            logging.error(f"[✗] Error processing batch: {e}")
                            failed_urls = thread_map[future]
                            for failed_url in failed_urls:
                                progress_tracker.update_url_status(
                                    failed_url,
                                    status=progress_tracker.URL_STATUS_FAILED,
                                )

                finally:
                    if not self.exit_handler.exit_requested:
                        progress_tracker.close()

            # Update download processing section
            try:
                pending_downloads = progress_tracker.get_pending_downloads()
                if not pending_downloads.empty:
                    logging.info(
                        f"[📥] Processing {len(pending_downloads)} pending downloads..."
                    )
                    self.download_manager.process_downloads(
                        pending_downloads, progress_tracker
                    )
            except Exception as e:
                logging.error(f"[✗] Error processing pending downloads: {e}")

        except Exception as e:
            logging.error(f"[✗] Fatal error in URL collection process: {e}")
            if not self.exit_handler.exit_requested:
                progress_tracker.close()

    def get_failed_urls(self, progress_tracker):
        """Get URLs that failed during collection"""
        df = pd.read_csv(progress_tracker.progress_file)
        return df[df["url_status"] == progress_tracker.URL_STATUS_FAILED][
            "page_url"
        ].tolist()

    def process_all_urls(
        self, batch_processor, safe_collector, headless, progress_tracker
    ):
        """Process all URLs including retries for failed ones"""
        while True:
            # Process URLs
            self.process_url_collection(
                batch_processor, safe_collector, headless, progress_tracker
            )

            # Check for failed URLs
            failed_urls = self.get_failed_urls(progress_tracker)
            if not failed_urls:
                logging.info("No failed URLs to retry")
                break

            logging.info(f"Found {len(failed_urls)} failed URLs")
            retry = input("Retry failed URLs? (y/n): ")
            if retry.lower() != "y":
                break

            # Create new batch processor with failed URLs
            retry_processor = BatchProcessor()
            retry_processor.urls = failed_urls

            logging.info("Retrying failed URLs...")
            # Keep track of original progress data
            df = pd.read_csv(progress_tracker.progress_file)

            # Process failed URLs
            self.process_url_collection(
                retry_processor, safe_collector, headless, progress_tracker
            )

            # Update progress file - replace old failed entries with new results
            new_df = pd.read_csv(progress_tracker.progress_file)
            for url in failed_urls:
                # Get new result for the URL
                new_result = new_df[new_df["page_url"] == url].iloc[0]
                # Update original dataframe with new result
                df.loc[df["page_url"] == url] = new_result

            # Save updated progress
            df.to_csv(progress_tracker.progress_file, index=False)

            logging.info("Progress file updated with retry results")
