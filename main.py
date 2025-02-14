import os
import asyncio
from playwright.sync_api import sync_playwright  # type: ignore
from utils.download import process_excel_file, process_url
from utils.login import google_login, get_credentials, save_cookies, load_cookies
from utils.parallel import BrowserManager
from utils.url_collector import UrlCollector
from utils.progress import ProgressTracker

# Path to the "batches" folder
links_folder = "./batches"

# Initialize a list to store all URLs
saved_urls = []

# Get Google account credentials
google_email, google_password = get_credentials()


# Main function to process all Excel files in the folder
def process_links_folder(links_folder):
    # Loop through all files in the "links" folder
    for file_name in os.listdir(links_folder):
        # Check if the file matches the pattern Batch_[number].xlsx
        if file_name.startswith("Batch_") and file_name.endswith(".xlsx"):
            file_path = os.path.join(links_folder, file_name)
            process_excel_file(file_path, saved_urls=saved_urls)


async def main():
    url_collector = UrlCollector()
    progress_tracker = ProgressTracker()

    # Process Excel files and get unprocessed URLs
    process_links_folder(links_folder)
    all_urls = progress_tracker.filter_unprocessed_urls(saved_urls)

    # Filter out already processed URLs
    unprocessed_urls = url_collector.get_unprocessed_urls(all_urls)

    if not unprocessed_urls:
        print("No new URLs to process!")
        return

    print(f"\nFound {len(unprocessed_urls)} unprocessed URLs")
    print(f"Skipping {len(all_urls) - len(unprocessed_urls)} already processed URLs")

    # Initialize single browser
    browser_manager = BrowserManager(google_email, google_password, headless=False)
    page = await browser_manager.initialize()

    try:
        # Process URLs sequentially
        print("\nCollecting download URLs...")
        url_collector.init_progress_bar(len(unprocessed_urls))

        for url in unprocessed_urls:
            await url_collector.collect_urls(page, url)
        url_collector.close()

        # Process downloads
        downloads = url_collector.load_pending_downloads()
        if downloads:
            print(f"\nDownloading {len(downloads)} files...")
            progress_tracker.init_progress_bar(len(downloads))

            for download in downloads:
                await url_collector.process_url(
                    page=page,
                    url=download["url"],
                    file_type=download["type"],
                    progress_tracker=progress_tracker,
                )
            progress_tracker.close()
        else:
            print("\nNo download URLs found!")

    finally:
        await browser_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
