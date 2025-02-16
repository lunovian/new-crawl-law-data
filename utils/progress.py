import csv
import os
from datetime import datetime
import pandas as pd
from tqdm.asyncio import tqdm
import shutil
from pathlib import Path


class ProgressTracker:
    # Add status constants
    URL_STATUS_PENDING = "PENDING"
    URL_STATUS_FOUND = "FOUND"
    URL_STATUS_FAILED = "FAILED"

    DOWNLOAD_STATUS_NOT_STARTED = "NOT_STARTED"
    DOWNLOAD_STATUS_DONE = "DONE"
    DOWNLOAD_STATUS_FAILED = "FAILED"

    def __init__(self, progress_file="./download_urls.csv"):
        self.progress_file = progress_file
        self.processed_urls = self._load_processed_urls()
        self.pbar = None

    def _create_progress_file(self):
        """Create progress tracking CSV file with headers"""
        df = pd.DataFrame(
            columns=[
                "timestamp",
                "page_url",
                "doc_url",
                "pdf_url",
                "url_status",
                "download_status",
            ]
        )
        # Set proper dtypes for columns
        df = df.astype(
            {
                "timestamp": "str",
                "page_url": "str",
                "doc_url": "str",
                "pdf_url": "str",
                "url_status": "str",
                "download_status": "str",
            }
        )
        df.to_csv(self.progress_file, index=False)

    def _load_processed_urls(self):
        """Load previously processed URLs from progress file"""
        if not os.path.exists(self.progress_file):
            self._create_progress_file()
            return set()

        try:
            df = pd.read_csv(self.progress_file)
            # Use constants instead of strings
            return set(
                df[
                    (df["url_status"] == self.URL_STATUS_FOUND)
                    & (df["download_status"] == self.DOWNLOAD_STATUS_DONE)
                ]["page_url"].tolist()
            )
        except Exception as e:
            print(f"Error loading progress file: {e}")
            self._create_progress_file()
            return set()

    def is_url_processed(self, url):
        """Check if URL has been fully processed and downloaded"""
        return url in self.processed_urls

    def filter_unprocessed_urls(self, urls):
        """Filter out already processed URLs"""
        return [url for url in urls if not self.is_url_processed(url)]

    def init_progress_bar(self, total):
        """Initialize progress bar"""
        if self.pbar:
            self.pbar.close()
        self.pbar = tqdm(
            total=total,
            desc="Processing",
            unit="url",
            dynamic_ncols=True,
            position=0,
            leave=True,
        )

    def update_progress(self, n=1):
        """Update progress bar"""
        if self.pbar:
            self.pbar.update(n)

    def update_url_status(
        self, page_url, doc_url="", pdf_url="", status=URL_STATUS_PENDING
    ):
        """Update URL collection status"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        df = pd.read_csv(self.progress_file)
        # Convert columns to string type
        for col in ["doc_url", "pdf_url"]:
            df[col] = df[col].astype("str").replace("nan", "")

        row = {
            "timestamp": timestamp,
            "page_url": str(page_url),
            "doc_url": str(doc_url) if doc_url else "",
            "pdf_url": str(pdf_url) if pdf_url else "",
            "url_status": status,
            "download_status": self.DOWNLOAD_STATUS_NOT_STARTED,
        }

        if page_url in df["page_url"].values:
            for col, val in row.items():
                df.loc[df["page_url"] == page_url, col] = val
        else:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

        df.to_csv(self.progress_file, index=False)

    def update_download_status(self, page_url, status):
        """Update download status for a URL"""
        df = pd.read_csv(self.progress_file)

        if page_url in df["page_url"].values:
            df.loc[df["page_url"] == page_url, "download_status"] = status
            if status == self.DOWNLOAD_STATUS_DONE:
                self.processed_urls.add(page_url)

            df.to_csv(self.progress_file, index=False)

            if self.pbar:
                self.pbar.set_postfix_str(f"Download: {status}")

    def get_pending_downloads(self):
        """Get URLs that need downloading"""
        df = pd.read_csv(self.progress_file)
        return df[
            (df["url_status"] == self.URL_STATUS_FOUND)
            & (df["download_status"] == self.DOWNLOAD_STATUS_NOT_STARTED)
        ]

    def close(self):
        """Close progress bar"""
        if self.pbar:
            self.pbar.close()
