import os
from typing import List
import pandas as pd
from .progress import ProgressTracker
import logging


class BatchProcessor:
    def __init__(self):
        self.urls = pd.DataFrame()
        self.progress_tracker = ProgressTracker()

    def get_urls(self) -> pd.DataFrame:
        """Get URLs as DataFrame

        Returns:
            pd.DataFrame: DataFrame with 'url' column
        """
        return self.urls

    def process_excel_file(self, file_path: str) -> None:
        """Process a single Excel file and extract URLs

        Args:
            file_path: Path to Excel file
        """
        try:
            df = pd.read_excel(file_path)

            # Handle different possible column names
            url_column = next(
                (
                    col
                    for col in df.columns
                    if col.lower() in ["url", "urls", "link", "links"]
                ),
                None,
            )

            if not url_column:
                raise ValueError(f"No URL column found in {file_path}")

            # Clean and validate URLs
            urls = df[url_column].astype(str)
            urls = urls[urls.str.contains("http", case=False, na=False)]

            # Update DataFrame
            if self.urls.empty:
                self.urls = pd.DataFrame({"url": urls})
            else:
                self.urls = pd.concat(
                    [self.urls, pd.DataFrame({"url": urls})], ignore_index=True
                )

            logging.info(
                f"[✓] Processed {len(urls)} URLs from {os.path.basename(file_path)}"
            )

        except Exception as e:
            logging.error(f"[✗] Error processing {file_path}: {str(e)}")
            raise

    def process_folder(self, folder_path: str) -> List[str]:
        """Process all Excel files in the specified folder

        Args:
            folder_path: Path to folder containing Excel files

        Returns:
            List[str]: List of processed URLs
        """
        if not os.path.exists(folder_path):
            raise FileNotFoundError(f"[✗] Folder not found: {folder_path}")

        try:
            # Process each Excel file
            for file_name in os.listdir(folder_path):
                if file_name.startswith("Batch_") and file_name.endswith(".xlsx"):
                    file_path = os.path.join(folder_path, file_name)
                    self.process_excel_file(file_path)

            # Remove duplicates
            self.urls.drop_duplicates(subset=["url"], inplace=True)
            logging.info(f"[✓] Total unique URLs found: {len(self.urls)}")

            return self.urls["url"].tolist()

        except Exception as e:
            logging.error(f"[✗] Error processing folder {folder_path}: {str(e)}")
            raise
