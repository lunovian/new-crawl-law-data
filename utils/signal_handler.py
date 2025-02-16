import signal
import os
from datetime import datetime
import pandas as pd


class GracefulExitHandler:
    def __init__(self):
        self.progress_tracker = None
        self.url_collector = None
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def register_components(self, progress_tracker=None, url_collector=None):
        self.progress_tracker = progress_tracker
        self.url_collector = url_collector

    def _handle_exit(self, signum, frame):
        """Clean exit handler for interrupts"""
        print("\n\nReceived interrupt signal. Cleaning up...")

        try:
            if self.progress_tracker:
                # Save final stats
                df = pd.read_csv(self.progress_tracker.progress_file)
                stats = {
                    "Total URLs": len(df),
                    "Found": len(df[df["url_status"] == "FOUND"]),
                    "Failed": len(df[df["url_status"] == "FAILED"]),
                    "Downloads Complete": len(df[df["download_status"] == "DONE"]),
                    "Downloads Pending": len(
                        df[df["download_status"] == "NOT_STARTED"]
                    ),
                }

                print("\nFinal Statistics:")
                for key, value in stats.items():
                    print(f"{key}: {value}")

                # Save summary to log
                with open("exit_summary.log", "a") as f:
                    f.write(f"\n--- Exit Summary {datetime.now()} ---\n")
                    for key, value in stats.items():
                        f.write(f"{key}: {value}\n")

            if self.url_collector and hasattr(self.url_collector, "browser"):
                self.url_collector.browser.close()

        except Exception as e:
            print(f"Error during cleanup: {e}")

        print("\nExiting gracefully...")
        if os.name == "nt":  # Windows
            os.system("cls")
