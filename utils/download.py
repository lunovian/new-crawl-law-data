# Function to process an Excel file
import os
import pandas as pd
from utils.rename_file import rename_downloaded_file
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count
import asyncio
import requests
from tqdm import tqdm


# Download threads (can be more aggressive)
download_threads = min(cpu_count() * 2, 8)  # Cap at 8
download_threads = max(4, download_threads)  # Minimum 4


def download_file(url, filepath):
    """Download file directly from URL"""
    try:
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
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            return True
        else:
            print(f"Download failed with status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Download error: {e}")
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


def download_through_urls(page, url, progress_tracker):
    try:
        # Read download URLs from CSV
        csv_path = "./download_urls.csv"
        if not os.path.exists(csv_path):
            raise Exception(f"Download URLs file not found: {csv_path}")

        # Read CSV with specified column names
        df = pd.read_csv(csv_path)

        # Filter URLs for current document
        current_doc = df[df["page_url"] == url]
        if current_doc.empty:
            raise Exception("No entries found for this URL")

        # Get both doc and pdf URLs, handle duplicates
        doc_urls = current_doc["doc_url"].drop_duplicates().dropna().tolist()
        pdf_urls = current_doc["pdf_url"].drop_duplicates().dropna().tolist()

        # Combine valid URLs (no need to filter duplicates since they're direct download links)
        static_urls = doc_urls + pdf_urls

        if not static_urls:
            raise Exception("No valid download URLs found for this document")

        # Print URL summary
        print(f"\nFound URLs for {url}:")
        print(f"- DOC files: {len(doc_urls)}")
        print(f"- PDF files: {len(pdf_urls)}")
        print(f"- Total files: {len(static_urls)}")

        # Initialize downloaded_files list at the start
        downloaded_files = []

        # Prepare download tasks
        downloads_dir = "./downloads"
        download_tasks = []

        for static_url in static_urls:
            file_type = "pdf" if static_url.lower().endswith(".pdf") else "doc"
            type_dir = os.path.join(downloads_dir, file_type)
            os.makedirs(type_dir, exist_ok=True)

            new_filename = rename_downloaded_file("", url, file_type)
            filepath = os.path.join(type_dir, new_filename)

            # Skip if file already exists
            if os.path.exists(filepath):
                print(f"\nSkipping existing file: {new_filename}")
                downloaded_files.append(file_type)
                continue

            download_tasks.append((static_url, filepath, file_type))

        # Calculate optimal thread count
        num_threads = min(cpu_count() - 1, len(download_tasks))
        num_threads = max(2, num_threads)  # At least 2 threads

        print(f"\nStarting downloads with {num_threads} threads")

        # Process downloads in parallel
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            results = list(executor.map(download_file_worker, download_tasks))
            downloaded_files.extend([r for r in results if r is not None])

        if downloaded_files:
            progress_tracker.update_progress(
                url=url,
                status="SUCCESS",
                file_types=downloaded_files,
                static_urls=static_urls,
            )
            print(f"\nSuccessfully downloaded {len(downloaded_files)} files")
        else:
            raise Exception("No files were downloaded successfully")

    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        progress_tracker.update_progress(url, "ERROR", None, str(e))
        return False


def process_pending_downloads(df, progress_tracker):
    """Process pending downloads from CSV"""
    download_tasks = []
    downloads_dir = "./downloads"

    for _, row in df.iterrows():
        for url_type in ["doc_url", "pdf_url"]:
            if pd.notna(row[url_type]):
                file_type = "doc" if url_type == "doc_url" else "pdf"
                type_dir = os.path.join(downloads_dir, file_type)
                os.makedirs(type_dir, exist_ok=True)

                new_filename = rename_downloaded_file("", row["page_url"], file_type)
                filepath = os.path.join(type_dir, new_filename)

                if not os.path.exists(filepath):
                    download_tasks.append(
                        (row[url_type], filepath, file_type, row["page_url"])
                    )

    if download_tasks:
        print(f"\nStarting downloads with {download_threads} threads")
        print(f"Total files to download: {len(download_tasks)}")

        progress_tracker.init_progress_bar(len(download_tasks))

        # Process downloads in parallel
        with ThreadPoolExecutor(max_workers=download_threads) as executor:
            results = list(executor.map(download_file_worker, download_tasks))

            # Update progress for each download
            for task, result in zip(download_tasks, results):
                page_url = task[3]  # Get the original page URL
                status = (
                    progress_tracker.DOWNLOAD_STATUS_DONE
                    if result
                    else progress_tracker.DOWNLOAD_STATUS_FAILED
                )
                progress_tracker.update_download_status(page_url, status)

        progress_tracker.close()
