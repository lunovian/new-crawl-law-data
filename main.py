import os
import math
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
from threading import Lock
from utils.login import (
    get_credentials,
)
from utils.url_collector import UrlCollector
from utils.progress import ProgressTracker
from utils.download import process_pending_downloads
from utils.batch_processor import BatchProcessor
import pandas as pd
import argparse


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


def main():
    args = parse_args()
    headless = not args.no_headless

    # Initialize components
    progress_tracker = ProgressTracker()
    batch_processor = BatchProcessor()
    safe_collector = ThreadSafeCollector()
    url_collector = UrlCollector()

    while True:
        # First check and process existing downloads
        if os.path.exists(progress_tracker.progress_file):
            pending_downloads = progress_tracker.get_pending_downloads()
            if not pending_downloads.empty:
                print(f"\nFound {len(pending_downloads)} pending downloads")
                process_pending_downloads(pending_downloads, progress_tracker)

        # Process URLs (including retries for failed ones)
        url_collector.process_all_urls(
            batch_processor, safe_collector, headless, progress_tracker
        )

        # Check final status
        df = pd.read_csv(progress_tracker.progress_file)
        failed_urls = len(df[df["url_status"] == progress_tracker.URL_STATUS_FAILED])
        pending_downloads = len(progress_tracker.get_pending_downloads())

        print("\nFinal Status:")
        print(f"Failed URLs: {failed_urls}")
        print(f"Pending Downloads: {pending_downloads}")

        if failed_urls == 0 and pending_downloads == 0:
            print("\nAll URLs processed and downloads completed!")
            break

        retry = input("\nContinue processing? (y/n): ")
        if retry.lower() != "y":
            break


if __name__ == "__main__":
    main()
