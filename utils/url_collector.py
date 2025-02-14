import asyncio
import csv
import os
import time
from datetime import datetime
from tqdm import tqdm
from bs4 import BeautifulSoup
import re
from playwright.async_api import Error as PlaywrightError, TimeoutError
from utils.download import download_file
from utils.rename_file import rename_downloaded_file
import logging
import json


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

    def init_progress_bar(self, total):
        """Initialize progress bar"""
        self.pbar = tqdm(total=total, desc="Collecting URLs", unit="url")

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

    async def collect_urls(self, page, url):
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
                await page.route(
                    "**/*.{png,jpg,jpeg,gif,css,woff,woff2}",
                    lambda route: route.abort(),
                )

                # Navigate with timeout
                await page.goto(
                    url, wait_until="domcontentloaded", timeout=self.timeout
                )

                # Get page content
                html_content = await page.content()
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
                await asyncio.sleep(2**attempt)
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

    async def process_url(self, page, url, file_type, progress_tracker):
        """Process URL download with specific error handling"""
        try:
            print(f"\nProcessing {file_type.upper()} URL: {url}")
            await page.goto(url, wait_until="domcontentloaded")

            # Get cookies for download
            cookies = {
                cookie["name"]: cookie["value"]
                for cookie in await page.context.cookies()
            }

            # Download file
            downloads_dir = "./downloads"
            type_dir = os.path.join(downloads_dir, file_type)
            os.makedirs(type_dir, exist_ok=True)

            new_filename = rename_downloaded_file("", url, file_type)
            filepath = os.path.join(type_dir, new_filename)

            if await download_file(url, filepath, cookies):
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
