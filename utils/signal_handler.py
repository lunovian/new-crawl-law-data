import signal
import os
import logging
import threading
import time
import psutil
import ctypes
from datetime import datetime
import pandas as pd
from typing import Any
from concurrent.futures import ThreadPoolExecutor


class ExitHandler:
    """Handles graceful shutdown on interrupt signals with thread and process management"""

    def __init__(self):
        self.progress_tracker = None
        self.url_collector = None
        self.download_manager = None
        self.exit_requested = False
        self.exit_timeout = 30  # seconds to wait for graceful shutdown
        self.active_threads = set()
        self._lock = threading.Lock()
        self.executors = set()

        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)
        logging.info("[✓] Exit handler initialized")

    def restore_terminal(self):
        """Restore Windows terminal state"""
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-10), 7)
            logging.debug("[✓] Terminal state restored")
        except Exception as e:
            logging.error(f"[✗] Terminal restoration error: {str(e)}")

    def _cleanup_processes(self):
        """Clean up browser processes"""
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    # Kill Chrome and Chromium processes
                    if any(
                        name in proc.info["name"].lower()
                        for name in ["chrome", "chromium"]
                    ):
                        os.kill(proc.info["pid"], signal.SIGTERM)
                        logging.debug(f"[✓] Terminated process: {proc.info['name']}")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            logging.error(f"[✗] Process cleanup error: {str(e)}")

    def _cleanup_threads(self) -> None:
        """Attempt to cleanup all running threads"""
        if not self.active_threads and not self.executors:
            return

        logging.info("[⚙] Cleaning up active threads...")

        # Shutdown all thread pool executors
        for executor in self.executors:
            try:
                executor.shutdown(wait=False)
                logging.info("[✓] Executor shutdown initiated")
            except Exception as e:
                logging.error(f"[✗] Error shutting down executor: {str(e)}")

        # Wait for threads to finish
        deadline = time.time() + self.exit_timeout
        while self.active_threads and time.time() < deadline:
            remaining = len(self.active_threads)
            logging.info(f"[⚙] Waiting for {remaining} threads to finish...")
            time.sleep(1)

        # Force terminate remaining threads
        if self.active_threads:
            logging.warning(f"[!] Force terminating {len(self.active_threads)} threads")

    def _handle_exit(self, signum, frame):
        """Enhanced exit handler with complete cleanup"""
        if self.exit_requested:
            logging.warning("[‼] Force exit requested, terminating immediately...")
            self.restore_terminal()
            os._exit(1)

        self.exit_requested = True
        logging.info("\n[⚠] Received interrupt signal. Starting cleanup...")

        try:
            # Cleanup threads first
            self._cleanup_threads()

            # Cleanup processes
            self._cleanup_processes()

            # Process final statistics
            if self.progress_tracker:
                try:
                    self._process_final_statistics()
                except Exception as e:
                    logging.error(f"[✗] Error processing final statistics: {str(e)}")

            # Component cleanup
            self._cleanup_components()

        except Exception as e:
            logging.error(f"[✗] Error during cleanup: {str(e)}")
        finally:
            # Restore terminal state
            self.restore_terminal()
            logging.info("\n[👋] Exiting gracefully...")
            os._exit(0)

    def _process_final_statistics(self):
        """Process and save final statistics"""
        df = pd.read_csv(self.progress_tracker.progress_file)
        stats = {
            "Total URLs": len(df),
            "Found": len(df[df["url_status"] == "FOUND"]),
            "Failed": len(df[df["url_status"] == "FAILED"]),
            "Downloads Complete": len(df[df["download_status"] == "DONE"]),
            "Downloads Pending": len(df[df["download_status"] == "NOT_STARTED"]),
            "Downloads Failed": len(df[df["download_status"] == "FAILED"]),
            "Active Threads": len(self.active_threads),
            "Time of Exit": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        logging.info("\n=== Final Statistics ===")
        for key, value in stats.items():
            logging.info(f"[📊] {key}: {value}")
        self._save_exit_summary(stats)

    def _cleanup_components(self):
        """Cleanup registered components"""
        if self.url_collector and hasattr(self.url_collector, "browser"):
            try:
                self.url_collector.browser.close()
                logging.info("[✓] Browser closed")
            except Exception as e:
                logging.error(f"[✗] Error closing browser: {str(e)}")

        if self.progress_tracker:
            try:
                self.progress_tracker.close()
                logging.info("[✓] Progress tracker closed")
            except Exception as e:
                logging.error(f"[✗] Error closing progress tracker: {str(e)}")

    def register_components(self, **components):
        """Register components for cleanup

        Args:
            **components: Component instances to track (progress_tracker, url_collector, download_manager)
        """
        if "progress_tracker" in components:
            self.progress_tracker = components["progress_tracker"]
        if "url_collector" in components:
            self.url_collector = components["url_collector"]
        if "download_manager" in components:
            self.download_manager = components["download_manager"]
        logging.debug("[⚙] Components registered with exit handler")

    def unregister_thread(self, thread: threading.Thread) -> None:
        """Unregister a completed thread

        Args:
            thread: Thread to remove from tracking
        """
        with self._lock:
            self.active_threads.discard(thread)
            logging.debug(f"[⚙] Unregistered thread: {thread.name}")

    def register_executor(self, executor: ThreadPoolExecutor) -> None:
        """Register a thread pool executor

        Args:
            executor: ThreadPoolExecutor to track
        """
        with self._lock:
            self.executors.add(executor)
            logging.debug("[⚙] Registered thread pool executor")

    def _cleanup_threads(self) -> None:
        """Attempt to cleanup all running threads"""
        if not self.active_threads and not self.executors:
            return

        logging.info("[⚙] Cleaning up active threads...")

        # Shutdown all thread pool executors
        for executor in self.executors:
            try:
                executor.shutdown(wait=False)
                logging.info("[✓] Executor shutdown initiated")
            except Exception as e:
                logging.error(f"[✗] Error shutting down executor: {str(e)}")

        # Wait for threads to finish
        deadline = time.time() + self.exit_timeout
        while self.active_threads and time.time() < deadline:
            remaining = len(self.active_threads)
            logging.info(f"[⚙] Waiting for {remaining} threads to finish...")
            time.sleep(1)

        # Force terminate remaining threads
        if self.active_threads:
            logging.warning(f"[!] Force terminating {len(self.active_threads)} threads")
