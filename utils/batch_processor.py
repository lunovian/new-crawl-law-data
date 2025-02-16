import os
import pandas as pd
from .progress import ProgressTracker


class BatchProcessor:
    def __init__(self):
        self.saved_urls = []
        self.progress_tracker = ProgressTracker()

    def process_excel_file(self, file_path):
        """Process a single Excel file and extract URLs"""
        try:
            df = pd.read_excel(file_path)
            urls = df["Url"].tolist()
            self.saved_urls.extend(urls)
            print(f"Processed {len(urls)} URLs from {os.path.basename(file_path)}")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    def process_folder(self, folder_path):
        """Process all Excel files in the specified folder"""
        if not os.path.exists(folder_path):
            raise Exception(f"Folder not found: {folder_path}")

        for file_name in os.listdir(folder_path):
            if file_name.startswith("Batch_") and file_name.endswith(".xlsx"):
                file_path = os.path.join(folder_path, file_name)
                self.process_excel_file(file_path)

        return self.saved_urls
