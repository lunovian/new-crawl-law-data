# Function to process an Excel file
import os
import logging
import requests
from tqdm import tqdm
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
from utils.rename_file import rename_downloaded_file
from utils.signal_handler import ExitHandler


class DownloadManager:
    """Manages multi-threaded downloads with exit handling"""

    def __init__(self):
        self.exit_handler = ExitHandler()
        self.download_threads = min(cpu_count() * 2, 8)  # Cap at 8
        self.download_threads = max(4, self.download_threads)  # Minimum 4
        self.chunk_size = 8192

    def _create_directory(self, directory: str) -> bool:
        """Create directory with proper permissions"""
        try:
            os.makedirs(directory, mode=0o777, exist_ok=True)
            os.chmod(directory, 0o777)  # Windows permissions
            return True
        except PermissionError:
            logging.error(f"[✗] Permission denied creating directory: {directory}")
            logging.error("[!] Try running with administrator privileges")
            return False
        except Exception as e:
            logging.error(f"[✗] Error creating directory {directory}: {str(e)}")
            return False

    def _verify_filepath(self, filepath: str) -> tuple[bool, str]:
        """Verify and prepare filepath"""
        try:
            filepath = os.path.normpath(filepath)
            directory = os.path.dirname(filepath)

            if directory and not self._create_directory(directory):
                return False, ""

            # Test file writability
            try:
                open(filepath, "wb").close()
                os.remove(filepath)
                return True, filepath
            except (PermissionError, OSError) as e:
                logging.error(f"[✗] Cannot write to {filepath}: {str(e)}")
                return False, ""

        except Exception as e:
            logging.error(f"[✗] Error verifying filepath: {str(e)}")
            return False, ""

    def download_file(self, url: str, filepath: str) -> bool:
        """Download file with progress bar and proper error handling"""
        try:
            # Verify filepath first
            success, verified_path = self._verify_filepath(filepath)
            if not success:
                return False

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36",
            }

            response = requests.get(url, headers=headers, stream=True)
            if response.status_code == 200:
                total_size = int(response.headers.get("content-length", 0))

                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    desc=os.path.basename(filepath),
                ) as pbar:
                    with open(verified_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                            if chunk and not self.exit_handler.exit_requested:
                                f.write(chunk)
                                pbar.update(len(chunk))
                            elif self.exit_handler.exit_requested:
                                logging.info(f"[⚠] Download interrupted: {url}")
                                return False
                return True
            else:
                logging.error(
                    f"[✗] Download failed (HTTP {response.status_code}): {url}"
                )
                return False

        except requests.exceptions.RequestException as e:
            logging.error(f"[✗] Network error downloading {url}: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"[✗] Error downloading {url}: {str(e)}")
            return False

    def download_worker(self, task: tuple) -> tuple:
        """Worker function for threaded downloads"""
        url, filepath, file_type, page_url = task

        try:
            # Skip if file exists and valid
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logging.info(f"[⏭] Skipping existing: {os.path.basename(filepath)}")
                return (True, page_url, "EXISTS")

            logging.info(f"[⚡] Downloading {file_type}: {url}")
            success = self.download_file(url, filepath)

            if success:
                logging.info(f"[✓] Downloaded: {os.path.basename(filepath)}")
                return (True, page_url, "DONE")
            else:
                logging.error(f"[✗] Failed: {url}")
                return (False, page_url, "FAILED")

        except Exception as e:
            logging.error(f"[✗] Worker error for {url}: {str(e)}")
            return (False, page_url, "ERROR")

    def process_downloads(self, df: pd.DataFrame, progress_tracker) -> None:
        """Process downloads using thread pool"""
        if df.empty:
            logging.info("[⚠] No pending downloads")
            return

        logging.info(f"\n[⚡] Processing {len(df)} downloads...")
        downloads_dir = os.path.abspath("downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        # Prepare download tasks
        tasks = []
        for _, row in df.iterrows():
            try:
                page_url = str(row["page_url"]).strip()
                url = str(row["url"]).strip()
                file_type = str(row["type"]).strip()

                if not all([page_url, url, file_type]):
                    logging.warning(f"[⚠] Invalid data: {row}")
                    continue

                type_dir = os.path.join(downloads_dir, file_type)
                os.makedirs(type_dir, exist_ok=True)

                safe_filename = rename_downloaded_file(url, page_url, file_type)
                filepath = os.path.join(type_dir, safe_filename)

                tasks.append((url, filepath, file_type, page_url))

            except Exception as e:
                logging.error(f"[✗] Task preparation error: {str(e)}")
                if "page_url" in locals():
                    progress_tracker.update_download_status(
                        page_url, progress_tracker.DOWNLOAD_STATUS_FAILED
                    )

        # Process downloads with thread pool
        with ThreadPoolExecutor(max_workers=self.download_threads) as executor:
            self.exit_handler.register_executor(executor)
            futures = {}

            try:
                # Submit tasks
                for task in tasks:
                    if self.exit_handler.exit_requested:
                        logging.info("[⚠] Exit requested, stopping new downloads")
                        break

                    future = executor.submit(self.download_worker, task)
                    futures[future] = task

                # Process results
                for future in as_completed(futures):
                    if self.exit_handler.exit_requested:
                        logging.info("[⚠] Exit requested, finishing current downloads")
                        break

                    try:
                        success, page_url, status = future.result(timeout=300)
                        if status == "EXISTS":
                            progress_tracker.update_download_status(
                                page_url, progress_tracker.DOWNLOAD_STATUS_DONE
                            )
                        else:
                            progress_tracker.update_download_status(
                                page_url,
                                progress_tracker.DOWNLOAD_STATUS_DONE
                                if success
                                else progress_tracker.DOWNLOAD_STATUS_FAILED,
                            )
                    except Exception as e:
                        url = futures[future][0]
                        logging.error(f"[✗] Download failed for {url}: {str(e)}")
                        progress_tracker.update_download_status(
                            futures[future][3], progress_tracker.DOWNLOAD_STATUS_FAILED
                        )

            finally:
                if not self.exit_handler.exit_requested:
                    logging.info("[✓] Download processing completed")
