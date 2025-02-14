import csv
import os
from datetime import datetime
import pandas as pd
from tqdm.asyncio import tqdm
import shutil
from pathlib import Path


class ProgressTracker:
    def __init__(self, progress_file="progress.csv"):
        self.progress_file = progress_file
        self.processed_urls = self._load_processed_urls()
        self.pbar = None

    def _migrate_old_progress_file(self):
        """Migrate old format progress file to new format"""
        try:
            # Create backup of old file
            backup_file = self.progress_file + ".backup"
            shutil.copy2(self.progress_file, backup_file)
            print(f"Created backup of old progress file at: {backup_file}")

            # Read old file
            df = pd.read_csv(self.progress_file)

            # Create new file with correct format
            self._create_progress_file()

            # Migrate old data
            with open(self.progress_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for _, row in df.iterrows():
                    writer.writerow(
                        [
                            row.get("timestamp", ""),
                            row.get("url", ""),
                            "",  # doc_url
                            "",  # pdf_url
                            row.get("status", ""),
                            row.get("file_types", ""),
                            row.get("error", ""),
                        ]
                    )

            print("Successfully migrated progress file to new format")
            return True
        except Exception as e:
            print(f"Error migrating progress file: {e}")
            # Restore backup if exists
            if os.path.exists(backup_file):
                shutil.copy2(backup_file, self.progress_file)
                print("Restored backup file")
            return False

    def _load_processed_urls(self):
        """Load previously processed URLs from progress file"""
        if not os.path.exists(self.progress_file):
            self._create_progress_file()
            return set()

        try:
            df = pd.read_csv(self.progress_file)
            return set(df[df["status"] == "SUCCESS"]["url"].tolist())
        except pd.errors.ParserError:
            print("Detected old progress file format, attempting migration...")
            if self._migrate_old_progress_file():
                # Try loading again after migration
                df = pd.read_csv(self.progress_file)
                return set(df[df["status"] == "SUCCESS"]["url"].tolist())
            else:
                print("Migration failed, creating new progress file")
                self._create_progress_file()
                return set()
        except Exception as e:
            print(f"Error loading progress file: {e}")
            self._create_progress_file()
            return set()

    def _create_progress_file(self):
        """Create progress tracking CSV file with headers"""
        with open(self.progress_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "timestamp",
                    "url",
                    "doc_url",
                    "pdf_url",
                    "status",
                    "file_types",
                    "error",
                ]
            )

    def is_url_processed(self, url):
        """Check if URL has been successfully processed"""
        return url in self.processed_urls

    def filter_unprocessed_urls(self, urls):
        """Filter out already processed URLs"""
        return [url for url in urls if not self.is_url_processed(url)]

    def init_progress_bar(self, total):
        """Initialize progress bar"""
        self.pbar = tqdm(
            total=total, desc="Processing URLs", unit="url", dynamic_ncols=True
        )

    def update_progress(
        self, url, status, file_types=None, error=None, static_urls=None
    ):
        """Update progress in CSV and progress bar with separate static URLs"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Separate DOC and PDF URLs
        doc_url = ""
        pdf_url = ""
        if static_urls:
            for static_url in static_urls:
                if static_url.lower().endswith(".pdf"):
                    pdf_url = static_url
                else:
                    doc_url = static_url

        with open(self.progress_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    timestamp,
                    url,
                    doc_url,
                    pdf_url,
                    status,
                    ",".join(file_types) if file_types else "",
                    str(error) if error else "",
                ]
            )

        if status == "SUCCESS":
            self.processed_urls.add(url)

        if self.pbar:
            self.pbar.update(1)
            self.pbar.set_postfix_str(f"Last: {status}")

    def close(self):
        """Close progress bar"""
        if self.pbar:
            self.pbar.close()
