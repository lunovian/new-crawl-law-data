import os
import csv
import pandas as pd
import logging


class ProgressTracker:
    # Add status constants
    URL_STATUS_PENDING = "PENDING"
    URL_STATUS_FOUND = "FOUND"
    URL_STATUS_FAILED = "FAILED"
    URL_STATUS_SKIPPED = "SKIPPED"

    DOWNLOAD_STATUS_NOT_STARTED = "NOT_STARTED"
    DOWNLOAD_STATUS_DONE = "DONE"
    DOWNLOAD_STATUS_FAILED = "FAILED"

    def __init__(self, progress_file="./download_urls.csv"):
        self.progress_file = progress_file
        self.total_urls = 0

        self.progress_threshold = 100
        self.processed_count = 0

        self._init_file()

    def _init_file(self):
        """Initialize CSV file if it doesn't exist"""
        if not os.path.exists(self.progress_file):
            with open(self.progress_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "page_url",
                        "doc_url",
                        "pdf_url",
                        "url_status",
                        "download_status",
                    ]
                )

    def set_total_urls(self, total):
        """Set total number of URLs to process"""
        self.total_urls = total
        print(f"\nStarting processing of {total} URLs")

    def update_progress(self, url, status, doc_url="", pdf_url=""):
        """Update progress with count and detailed information"""
        if self.total_urls == 0:
            return  # Prevent division by zero

        self.processed_count += 1

        # Always show current count with percentage
        percentage = (self.processed_count / self.total_urls) * 100
        print(
            f"\rProcessed: {self.processed_count}/{self.total_urls} ({percentage:.1f}%)",
            end="",
        )

        # Show detailed stats at threshold
        if self.processed_count % self.progress_threshold == 0:
            df = pd.read_csv(self.progress_file)
            found = len(df[df["url_status"] == self.URL_STATUS_FOUND])
            failed = len(df[df["url_status"] == self.URL_STATUS_FAILED])
            skipped = len(df[df["url_status"] == self.URL_STATUS_SKIPPED])

            print(f"\n{'=' * 50}")
            print(f"Progress Update at {self.processed_count} URLs:")
            print(f"Last URL: {url}")
            print(f"Status: {status}")
            if found > 0:
                print(f"Found: {found} ({found / self.processed_count * 100:.1f}%)")
            if failed > 0:
                print(f"Failed: {failed} ({failed / self.processed_count * 100:.1f}%)")
            if skipped > 0:
                print(
                    f"Skipped: {skipped} ({skipped / self.processed_count * 100:.1f}%)"
                )
            print(f"{'=' * 50}\n")

    def process_folder(self, folder_path):
        """Process all Excel files in the folder and return unique URLs"""
        all_urls = []

        # Create folder if it doesn't exist
        os.makedirs(folder_path, exist_ok=True)

        # Get all Excel files in the folder
        excel_files = [
            f for f in os.listdir(folder_path) if f.endswith((".xlsx", ".xls"))
        ]

        if not excel_files:
            print(f"No Excel files found in {folder_path}")
            return []

        # Process each Excel file
        for excel_file in excel_files:
            file_path = os.path.join(folder_path, excel_file)
            try:
                df = pd.read_excel(file_path)
                if "URL" in df.columns:  # Adjust column name if needed
                    urls = df["URL"].dropna().tolist()
                    all_urls.extend(urls)
            except Exception as e:
                print(f"Error processing {excel_file}: {e}")
                continue

        # Return unique URLs
        return list(set(all_urls))

    def filter_unprocessed_urls(self, urls):
        """Filter out already processed URLs"""
        if not os.path.exists(self.progress_file):
            return urls

        # Read processed URLs from CSV
        df = pd.read_csv(self.progress_file)
        processed_urls = set(df["page_url"].values)

        # Filter out processed URLs
        unprocessed_urls = [url for url in urls if url not in processed_urls]

        print(f"Total URLs: {len(urls)}")
        print(f"Already processed: {len(processed_urls)}")
        print(f"New URLs to process: {len(unprocessed_urls)}")

        return unprocessed_urls

    def get_pending_downloads(self):
        """Get URLs that need to be downloaded

        Returns:
            pandas.DataFrame: DataFrame with pending downloads
        """
        if os.path.exists(self.progress_file):
            df = pd.read_csv(self.progress_file)
            pending = []

            # Filter for FOUND status URLs
            found_urls = df[
                (df["url_status"] == self.URL_STATUS_FOUND)
                & (df["download_status"] == self.DOWNLOAD_STATUS_NOT_STARTED)
            ]

            for _, row in found_urls.iterrows():
                # Check and add doc URL if exists
                if pd.notna(row["doc_url"]):
                    pending.append(
                        {
                            "page_url": row["page_url"],
                            "url": row["doc_url"],
                            "type": "doc",
                        }
                    )

                # Check and add pdf URL if exists
                if pd.notna(row["pdf_url"]):
                    pending.append(
                        {
                            "page_url": row["page_url"],
                            "url": row["pdf_url"],
                            "type": "pdf",
                        }
                    )

            return pd.DataFrame(pending)
        return pd.DataFrame(columns=["page_url", "url", "type"])

    def update_download_status(self, page_url, status):
        """Update download status for a given URL"""
        try:
            if os.path.exists(self.progress_file):
                # Read CSV with string dtypes
                df = pd.read_csv(self.progress_file, dtype=str)

                # Ensure exact string matching
                mask = df["page_url"].astype(str) == str(page_url)

                if any(mask):
                    df.loc[mask, "download_status"] = status
                    df.to_csv(self.progress_file, index=False)
                    print(f"\nUpdated download status for {page_url} to {status}")
                else:
                    print(f"\nWarning: URL not found: {page_url}")

        except Exception as e:
            print(f"Error updating download status: {e}")
            logging.error(f"Failed to update download status for {page_url}: {e}")
