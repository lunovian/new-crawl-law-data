# Function to process an Excel file
import os
import pandas as pd
from utils.rename_file import rename_downloaded_file
import asyncio
import requests

# Remove the status_lock and save_download_status function as they're replaced by ProgressTracker


def process_excel_file(file_path, saved_urls):
    """
    Process an Excel file containing URLs and add them to saved_urls list.
    Returns True if successful, False otherwise.
    """
    try:
        # Read the Excel file into a DataFrame
        df = pd.read_excel(file_path)

        # Check if the required columns exist
        if "Url" not in df.columns:
            print(f"Error: File {file_path} does not contain the 'Url' column.")
            return False

        # Extract the 'Url' column and add it to the global list
        urls = df["Url"].dropna().tolist()  # Drop any NaN values

        # Check for duplicate URLs
        new_urls = [url for url in urls if url not in saved_urls]
        duplicates = len(urls) - len(new_urls)

        # Add new URLs to the list
        saved_urls.extend(new_urls)

        print(f"Processed {file_path}:")
        print(f"- Found {len(urls)} total URLs")
        print(f"- {len(new_urls)} new URLs added")
        if duplicates > 0:
            print(f"- {duplicates} duplicate URLs skipped")

        return True

    except pd.errors.EmptyDataError:
        print(f"Error: File {file_path} is empty")
        return False
    except Exception as e:
        print(f"Error processing {file_path}: {str(e)}")
        return False


# Function to process each URL after login
async def retry_goto(page, url, max_retries=3, timeout=60000):
    """Enhanced retry navigation with better error handling"""
    for attempt in range(max_retries):
        try:
            print(f"\nNavigating to {url} (Attempt {attempt + 1}/{max_retries})")

            # Clear navigation state
            await page.context.clear_cookies()
            try:
                await page.reload(timeout=5000)  # Quick reload to clear state
            except Exception as e:
                print(f"Reload failed: {e}")
                pass

            # First try: Basic navigation
            try:
                response = await page.goto(
                    url,
                    timeout=timeout,
                    wait_until="domcontentloaded",
                    referer="https://luatvietnam.vn",
                )

                if not response:
                    raise Exception("No response received")

                if response.status >= 400:
                    raise Exception(f"HTTP {response.status} error")

                # Verify we're on the correct page
                current_url = page.url
                if not current_url or "luatvietnam.vn" not in current_url:
                    raise Exception("Navigation redirected to wrong domain")

                # Wait for essential content
                try:
                    await page.wait_for_selector("div#divCenter", timeout=10000)
                except:
                    print("Warning: Content area not found")

                # Try to ensure page is fully loaded
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    print("Warning: Network not fully idle")

                print(f"Successfully loaded page: {current_url}")
                return True

            except Exception as e:
                print(f"First navigation attempt failed: {e}")

                # Second try: More aggressive approach
                await page.goto(
                    url,
                    timeout=timeout,
                    wait_until="commit",  # Less strict wait condition
                )

                # Manual checks
                await page.wait_for_timeout(2000)
                content = await page.content()
                if "luatvietnam.vn" not in content:
                    raise Exception("Page content verification failed")

        except Exception as e:
            wait_time = (2**attempt) * 2000  # Longer waits between retries
            print(f"Navigation attempt {attempt + 1} failed: {str(e)}")
            print(f"Waiting {wait_time / 1000} seconds before retry...")

            # Take screenshot for debugging
            try:
                await page.screenshot(path=f"nav_error_{attempt}.png")
            except:
                pass

            await asyncio.sleep(wait_time / 1000)

            if attempt == max_retries - 1:
                print("All navigation attempts failed")
                return False

    return False


async def wait_for_download_elements(page):
    """Wait for download elements with multiple strategies"""
    try:
        # First try waiting for elements to be present in DOM
        await page.wait_for_selector(
            "div.list-download, img.ic-download-vb",
            state="attached",  # Changed from 'visible' to 'attached'
            timeout=5000,
        )

        # Then ensure the content is loaded
        await page.wait_for_function(
            """() => {
                const elements = document.querySelectorAll('div.list-download, img.ic-download-vb');
                return Array.from(elements).some(el => 
                    window.getComputedStyle(el).display !== 'none' && 
                    window.getComputedStyle(el).visibility !== 'hidden'
                );
            }""",
            timeout=5000,
        )
    except Exception as e:
        print(f"Warning: Download elements detection warning: {e}")
        # Don't raise the exception, continue anyway


async def find_static_download_urls(page):
    """Extract static download URLs from the page"""
    try:
        static_urls = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href*="static.luatvietnam.vn"]'))
                .map(a => a.href)
                .filter(href => href.endsWith('.pdf') || href.endsWith('.doc') || href.endsWith('.docx'));
        }""")

        if static_urls:
            print("\nFound static download URLs:")
            for url in static_urls:
                print(f"- {url}")
            return static_urls

        return []
    except Exception as e:
        print(f"Error finding static URLs: {e}")
        return []


async def download_file(url, filepath, cookies):
    """Download file directly from static URL"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/119.0.0.0 Safari/537.36",
            "Referer": "https://luatvietnam.vn",
        }

        response = requests.get(url, cookies=cookies, headers=headers, stream=True)
        if response.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        else:
            print(f"Download failed with status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Download error: {e}")
        return False


async def process_url(page, url, progress_tracker):
    try:
        print(f"\nProcessing URL: {url}")
        await page.goto(url, wait_until="domcontentloaded")

        # Get static download URLs
        static_urls = await find_static_download_urls(page)
        if not static_urls:
            raise Exception("No static download URLs found")

        # Get cookies for download
        cookies = {
            cookie["name"]: cookie["value"] for cookie in await page.context.cookies()
        }

        # Download files
        downloads_dir = "./downloads"
        downloaded_files = []

        for static_url in static_urls:
            file_type = "pdf" if static_url.lower().endswith(".pdf") else "doc"
            type_dir = os.path.join(downloads_dir, file_type)
            os.makedirs(type_dir, exist_ok=True)

            new_filename = rename_downloaded_file("", url, file_type)
            filepath = os.path.join(type_dir, new_filename)

            print(f"\nDownloading {file_type.upper()}: {static_url}")
            if await download_file(static_url, filepath, cookies):
                print(f"Successfully downloaded: {new_filename}")
                downloaded_files.append(file_type)

        if downloaded_files:
            progress_tracker.update_progress(
                url=url,
                status="SUCCESS",
                file_types=downloaded_files,
                static_urls=static_urls,
            )
        else:
            raise Exception("No files were downloaded successfully")

    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        progress_tracker.update_progress(url, "ERROR", None, str(e))
