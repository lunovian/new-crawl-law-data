# Function to process an Excel file
import os
import pandas as pd
from utils.rename_file import rename_downloaded_file
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
import requests
from tqdm import tqdm


# Download threads (can be more aggressive)
download_threads = min(cpu_count() * 2, 8)  # Cap at 8
download_threads = max(4, download_threads)  # Minimum 4


def download_file(url, filepath):
    """Download file directly from URL with proper directory handling"""
    try:
        # Normalize filepath and ensure it has a filename
        filepath = os.path.normpath(filepath)
        if filepath.endswith(os.path.sep) or os.path.isdir(filepath):
            filename = os.path.basename(url)
            if not filename:  # If URL doesn't have a filename
                filename = "download"  # Default name
            filepath = os.path.join(filepath, filename)

        # Create directory with proper permissions
        directory = os.path.dirname(filepath)
        if directory:
            try:
                # Create directory with full permissions
                os.makedirs(directory, mode=0o777, exist_ok=True)
                # Ensure write permissions on Windows
                os.chmod(directory, 0o777)
            except PermissionError:
                print(f"Permission denied creating directory: {directory}")
                print("Try running VS Code as administrator")
                return False

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36",
        }

        # Download file
        response = requests.get(url, headers=headers, stream=True)
        if response.status_code == 200:
            total_size = int(response.headers.get("content-length", 0))

            try:
                # Ensure file path is writable
                with open(filepath, "wb") as test_file:
                    pass
                os.remove(filepath)  # Remove test file

                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    desc=os.path.basename(filepath),
                ) as pbar:
                    with open(filepath, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                return True

            except PermissionError as pe:
                print(f"Permission denied writing file: {filepath}")
                print("Error details:", str(pe))
                print("Try running VS Code as administrator")
                return False
            except OSError as ose:
                print(f"OS error writing file: {filepath}")
                print("Error details:", str(ose))
                return False

        else:
            print(f"Download failed with status code: {response.status_code}")
            return False

    except Exception as e:
        print(f"Download error: {str(e)}")
        return False


def download_file_worker(args):
    """Worker function for threaded downloads"""
    static_url, filepath, file_type = args

    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Skip if file exists and is valid
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        print(f"\nSkipping existing file: {os.path.basename(filepath)}")
        return file_type

    print(f"\nDownloading {file_type.upper()}: {static_url}")
    if download_file(static_url, filepath):
        print(f"Successfully downloaded: {os.path.basename(filepath)}")
        return file_type

    return None


def process_downloads(df, progress_tracker):
    """Process pending downloads from DataFrame"""
    if df.empty:
        print("No pending downloads")
        return

    print(f"\nProcessing {len(df)} pending downloads...")

    # Create base downloads directory with absolute path
    downloads_dir = os.path.abspath("downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    for _, row in df.iterrows():
        try:
            # Extract and validate values
            page_url = str(row["page_url"]).strip()
            url = str(row["url"]).strip()
            file_type = str(row["type"]).strip()

            if not all([page_url, url, file_type]):
                print(f"Missing required data for row: {row}")
                continue

            # Create type directory
            type_dir = os.path.join(downloads_dir, file_type)
            os.makedirs(type_dir, exist_ok=True)

            # Generate filename using rename_downloaded_file
            safe_filename = rename_downloaded_file(url, page_url, file_type)

            # Create full filepath
            filepath = os.path.join(type_dir, safe_filename)

            print(f"\nDownloading {file_type}: {url}")
            print(f"To: {filepath}")

            if download_file(url, filepath):
                print(f"✓ Successfully downloaded: {safe_filename}")
                progress_tracker.update_download_status(
                    page_url, progress_tracker.DOWNLOAD_STATUS_DONE
                )
            else:
                print(f"✗ Failed to download: {url}")
                progress_tracker.update_download_status(
                    page_url, progress_tracker.DOWNLOAD_STATUS_FAILED
                )

        except Exception as e:
            print(f"Error processing download: {str(e)}")
            if "page_url" in locals():
                progress_tracker.update_download_status(
                    page_url, progress_tracker.DOWNLOAD_STATUS_FAILED
                )

    print("\nDownload processing completed")
