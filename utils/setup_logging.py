import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


class Logger:
    """Custom logger with rotation and different log files"""

    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

        # Create different log files
        self.general_log = os.path.join(log_dir, "crawler.log")
        self.error_log = os.path.join(log_dir, "error.log")
        self.debug_log = os.path.join(log_dir, "debug.log")
        self.download_log = os.path.join(log_dir, "downloads.log")

        # Configure logging
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging with rotation and different handlers"""
        # Create formatters
        file_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_formatter = logging.Formatter("%(message)s")

        # Set up handlers with rotation
        general_handler = RotatingFileHandler(
            self.general_log,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding="utf-8",
        )
        error_handler = RotatingFileHandler(
            self.error_log, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        debug_handler = RotatingFileHandler(
            self.debug_log, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        download_handler = RotatingFileHandler(
            self.download_log, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        console_handler = logging.StreamHandler()

        # Set levels
        general_handler.setLevel(logging.INFO)
        error_handler.setLevel(logging.ERROR)
        debug_handler.setLevel(logging.DEBUG)
        download_handler.setLevel(logging.INFO)
        console_handler.setLevel(logging.INFO)

        # Set formatters
        general_handler.setFormatter(file_formatter)
        error_handler.setFormatter(file_formatter)
        debug_handler.setFormatter(file_formatter)
        download_handler.setFormatter(file_formatter)
        console_handler.setFormatter(console_formatter)

        # Configure root logger
        logging.root.setLevel(logging.DEBUG)
        logging.root.addHandler(general_handler)
        logging.root.addHandler(error_handler)
        logging.root.addHandler(debug_handler)
        logging.root.addHandler(download_handler)
        logging.root.addHandler(console_handler)

    def cleanup_old_logs(self, days=7):
        """Delete log files older than specified days"""
        current_time = datetime.now()
        for filename in os.listdir(self.log_dir):
            filepath = os.path.join(self.log_dir, filename)
            file_time = datetime.fromtimestamp(os.path.getctime(filepath))
            if (current_time - file_time).days > days:
                try:
                    os.remove(filepath)
                    logging.debug(f"Deleted old log file: {filename}")
                except Exception as e:
                    logging.error(f"Error deleting {filename}: {e}")
