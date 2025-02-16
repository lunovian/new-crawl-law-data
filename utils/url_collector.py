import asyncio
import csv
import os
import time
from datetime import datetime
from tqdm import tqdm
from bs4 import BeautifulSoup
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError
from playwright.sync_api import sync_playwright  # type: ignore
from utils.batch_processor import BatchProcessor
from utils.download import download_file
from utils.rename_file import rename_downloaded_file
import logging
import json
from utils.login import (
    get_credentials,
    google_login,
    save_cookies,
    load_cookies,
    verify_login,
)
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
import math


# URL collection threads (more conservative)
url_threads = min(cpu_count() - 1, 4)  # Cap at 4
url_threads = max(2, url_threads)  # Minimum 2

# Path to the "batches" folder
links_folder = "./batches"

# Initialize a list to store all URLs
saved_urls = []

# Get Google account credentials
google_email, google_password = get_credentials()


class UrlCollector:
    def __init__(self, urls_file="download_urls.csv"):
        self.urls_file = urls_file
        self.progress_file = "collection_progress.json"
        self._init_file()
        self.pbar = None
        self.url_cache = {}
        self.timeout = 30000
        self.max_retries = 3
        self.processed_urls = self._load_progress()

    def _load_progress(self):
        """Load previously processed URLs"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, "r") as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, FileNotFoundError):
                return set()
        return set()

    def _save_progress(self, url):
        """Save URL to progress file"""
        self.processed_urls.add(url)
        with open(self.progress_file, "w") as f:
            json.dump(list(self.processed_urls), f)

    def get_unprocessed_urls(self, urls):
        """Filter out already processed URLs"""
        return [url for url in urls if url not in self.processed_urls]

    def close(self):
        """Close progress bar"""
        if self.pbar:
            self.pbar.close()

    def _init_file(self):
        if not os.path.exists(self.urls_file):
            with open(self.urls_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["timestamp", "page_url", "doc_url", "pdf_url", "status"]
                )

    def collect_urls(self, page, url):
        """Collect URLs with progress tracking"""
        if url in self.processed_urls:
            print(f"Skipping already processed URL: {url}")
            if self.pbar:
                self.pbar.update(1)
                self.pbar.set_postfix_str("SKIP")
            return True

        for attempt in range(self.max_retries):
            try:
                # Block unwanted resources
                page.route(
                    "**/*.{png,jpg,jpeg,gif,css,woff,woff2}",
                    lambda route: route.abort(),
                )

                # Navigate with timeout
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                # Get page content
                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")

                # Find links
                static_links = {"doc": "", "pdf": ""}
                for link in soup.find_all(
                    "a", href=re.compile(r"static\.luatvietnam\.vn")
                ):
                    href = link["href"].lower()
                    if href.endswith(".pdf"):
                        static_links["pdf"] = href
                    elif any(href.endswith(ext) for ext in [".doc", ".docx"]):
                        static_links["doc"] = href
                    if static_links["doc"] and static_links["pdf"]:
                        break

                # Save results and progress
                if static_links["doc"] or static_links["pdf"]:
                    self.save_urls(
                        page_url=url,
                        doc_url=static_links["doc"],
                        pdf_url=static_links["pdf"],
                    )
                    self._save_progress(url)
                    if self.pbar:
                        self.pbar.update(1)
                        self.pbar.set_postfix_str("✓")
                    return True

                if attempt == self.max_retries - 1:
                    self.save_urls(url, "", "", status="FOUND")
                    self._save_progress(url)
                    if self.pbar:
                        self.pbar.update(1)
                        self.pbar.set_postfix_str("✗")
                    return False

            except (PlaywrightError, TimeoutError) as e:
                logging.error(f"Navigation error for {url}: {str(e)}")
                if attempt == self.max_retries - 1:
                    self.save_urls(url, "", "", status="ERROR")
                    self._save_progress(url)
                    if self.pbar:
                        self.pbar.update(1)
                        self.pbar.set_postfix_str("ERROR")
                    return False
                asyncio.sleep(2**attempt)
            except IOError as e:
                logging.error(f"IO error processing {url}: {str(e)}")
                self.save_urls(url, "", "", status="ERROR")
                self._save_progress(url)
                if self.pbar:
                    self.pbar.update(1)
                    self.pbar.set_postfix_str("ERROR")
                return False
            except Exception as e:
                logging.error(f"Unexpected error for {url}: {str(e)}")
                self.save_urls(url, "", "", status="ERROR")
                self._save_progress(url)
                if self.pbar:
                    self.pbar.update(1)
                    self.pbar.set_postfix_str("ERROR")
                return False

    def save_urls(self, page_url, doc_url="", pdf_url="", status="FOUND"):
        """Save URLs to CSV file"""
        with open(self.urls_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    page_url,
                    doc_url,
                    pdf_url,
                    status,
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
        batch_pbar = tqdm(
            total=len(urls), desc="Collecting URLs", unit="url", leave=False, position=1
        )

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

            page = context.new_page()

            try:
                # Handle login
                if load_cookies(context):
                    page = context.new_page()
                    if not verify_login(page):
                        google_login(page, google_email, google_password)
                        save_cookies(context)
                    page.close()
                else:
                    page = context.new_page()
                    google_login(page, google_email, google_password)
                    save_cookies(context)
                    page.close()

                # Process each URL
                for url in urls:
                    retry_count = 0
                    success = False

                    while retry_count < self.max_retries and not success:
                        try:
                            page = context.new_page()
                            doc_url, pdf_url = self.collect_urls(page, url)

                            if doc_url or pdf_url:
                                # Add to shared collector's downloads
                                downloads = []
                                if doc_url:
                                    downloads.append(
                                        {"page_url": url, "url": doc_url, "type": "doc"}
                                    )
                                if pdf_url:
                                    downloads.append(
                                        {"page_url": url, "url": pdf_url, "type": "pdf"}
                                    )
                                collector.add_downloads(downloads)
                                success = True
                                batch_pbar.set_postfix_str("✓")
                            else:
                                batch_pbar.set_postfix_str("✗")

                            # Store result regardless of success
                            results.append((url, doc_url, pdf_url))
                            break

                        except Exception as e:
                            print(
                                f"Attempt {retry_count + 1} failed for URL {url}: {e}"
                            )
                            retry_count += 1
                            if retry_count == self.max_retries:
                                results.append((url, "", ""))
                                batch_pbar.set_postfix_str("❌")
                        finally:
                            if "page" in locals():
                                page.close()
                            batch_pbar.update(1)

                return results

            finally:
                browser.close()
                batch_pbar.close()

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

    def process_url(self, page, url, file_type, progress_tracker):
        """Process URL download with specific error handling"""
        try:
            print(f"\nProcessing {file_type.upper()} URL: {url}")
            page.goto(url, wait_until="domcontentloaded")

            # Get cookies for download
            cookies = {
                cookie["name"]: cookie["value"] for cookie in page.context.cookies()
            }

            # Download file
            downloads_dir = "./downloads"
            type_dir = os.path.join(downloads_dir, file_type)
            os.makedirs(type_dir, exist_ok=True)

            new_filename = rename_downloaded_file("", url, file_type)
            filepath = os.path.join(type_dir, new_filename)

            if download_file(url, filepath, cookies):
                print(f"Successfully downloaded: {new_filename}")
                progress_tracker.update_progress(
                    url=url, status="SUCCESS", file_types=[file_type], static_urls=[url]
                )
            else:
                raise IOError("Download failed")

        except PlaywrightError as e:
            logging.error(f"Browser error downloading {url}: {str(e)}")
            progress_tracker.update_progress(
                url, "ERROR", None, f"Browser error: {str(e)}"
            )
        except TimeoutError as e:
            logging.error(f"Timeout downloading {url}: {str(e)}")
            progress_tracker.update_progress(url, "ERROR", None, f"Timeout: {str(e)}")
        except IOError as e:
            logging.error(f"IO error downloading {url}: {str(e)}")
            progress_tracker.update_progress(url, "ERROR", None, f"IO error: {str(e)}")
        except Exception as e:
            logging.error(f"Unexpected error downloading {url}: {str(e)}")
            progress_tracker.update_progress(
                url, "ERROR", None, f"Unexpected error: {str(e)}"
            )

    def process_url_collection(
        self, batch_processor, safe_collector, headless, progress_tracker
    ):
        """Process URL collection and new downloads"""
        try:
            # Process Excel files and get unprocessed URLs
            saved_urls = batch_processor.process_folder(links_folder)
            unprocessed_urls = progress_tracker.filter_unprocessed_urls(saved_urls)

            if not unprocessed_urls:
                print("No new URLs to process!")
                return

            print(f"\nFound {len(unprocessed_urls)} unprocessed URLs")

            # Calculate batch size and create batches
            try:
                batch_size = math.ceil(len(unprocessed_urls) / url_threads)
                url_batches = [
                    unprocessed_urls[i : i + batch_size]
                    for i in range(0, len(unprocessed_urls), batch_size)
                ]
            except Exception as e:
                print(f"Error creating URL batches: {e}")
                return

            # Print thread and batch information
            print(f"\nSystem CPU count: {cpu_count()}")
            print(f"Using {url_threads} threads (capped at 4, minimum 2)")
            print(f"Total URLs: {len(unprocessed_urls)}")
            print(f"Batch size: {batch_size} URLs per thread")

            # Initialize progress tracking
            progress_tracker.init_progress_bar(len(unprocessed_urls))

            # Prepare arguments for each thread - remove headless from args
            thread_args = [
                (
                    batch,  # urls
                    google_email,  # email
                    google_password,  # password
                    safe_collector.url_collector,  # collector_methods
                    headless,  # Add headless parameter
                )
                for batch in url_batches
            ]

            print("\nStarting URL collection...")
            # Process URL batches in parallel using threads
            with ThreadPoolExecutor(max_workers=url_threads) as executor:
                futures = []
                thread_map = {}  # Store batch URLs for error handling

                try:
                    # Update thread submission to include headless
                    for thread_arg in thread_args:
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
                            print(f"Error submitting batch to thread pool: {e}")
                            continue

                    # Process results as they complete
                    for future in futures:
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
                                        print(
                                            f"Error updating progress for URL {url}: {e}"
                                        )
                                        continue

                        except TimeoutError:
                            print("Batch processing timed out")
                            failed_urls = thread_map[future]
                            for failed_url in failed_urls:
                                progress_tracker.update_url_status(
                                    failed_url,
                                    status=progress_tracker.URL_STATUS_FAILED,
                                )
                        except Exception as e:
                            print(f"Error processing batch: {e}")
                            failed_urls = thread_map[future]
                            for failed_url in failed_urls:
                                progress_tracker.update_url_status(
                                    failed_url,
                                    status=progress_tracker.URL_STATUS_FAILED,
                                )

                finally:
                    progress_tracker.close()

            # Process pending downloads
            try:
                pending_downloads = progress_tracker.get_pending_downloads()
                if not pending_downloads.empty:
                    print(f"\nProcessing {len(pending_downloads)} pending downloads...")
                    self.process_pending_downloads(pending_downloads, progress_tracker)
            except Exception as e:
                print(f"Error processing pending downloads: {e}")

        except Exception as e:
            print(f"Fatal error in URL collection process: {e}")
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
                print("\nNo failed URLs to retry")
                break

            print(f"\nFound {len(failed_urls)} failed URLs")
            retry = input("Retry failed URLs? (y/n): ")
            if retry.lower() != "y":
                break

            # Create new batch processor with failed URLs
            retry_processor = BatchProcessor()
            retry_processor.urls = failed_urls

            print("\nRetrying failed URLs...")
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

            print("\nProgress file updated with retry results")
