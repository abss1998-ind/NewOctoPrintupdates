import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler


# Global flag for advanced debugging mode
ADVANCED_DEBUG_MODE = False

def set_advanced_debug_mode(enabled: bool):
    """Enable or disable advanced debugging mode globally."""
    global ADVANCED_DEBUG_MODE
    ADVANCED_DEBUG_MODE = enabled
    
    # Update all existing loggers
    root_logger = logging.getLogger()
    target_level = logging.DEBUG if enabled else logging.INFO
    
    # Update all handlers in all loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(target_level)
        for handler in logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.setLevel(target_level)

def get_advanced_debug_mode() -> bool:
    """Get the current advanced debugging mode state."""
    global ADVANCED_DEBUG_MODE
    return ADVANCED_DEBUG_MODE



# Try to use OctoPrint's logs directory, fallback to project root logs directory if not accessible
def get_log_dir():
    octoprint_logs = os.path.expanduser('/home/pi/.octoprint/logs')
    try:
        os.makedirs(octoprint_logs, exist_ok=True)
        # Test write access
        testfile = os.path.join(octoprint_logs, 'cc_log_test.tmp')
        with open(testfile, 'w') as f:
            f.write('test')
        os.remove(testfile)
        print(f"Using OctoPrint logs directory: {octoprint_logs}")
        return octoprint_logs
    except Exception:
        # Fallback to project root logs directory
        print("Could not access OctoPrint logs directory, using fallback.")
        fallback_logs = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'logs'))
        os.makedirs(fallback_logs, exist_ok=True)
        return fallback_logs

LOG_DIR = get_log_dir()
LOG_FILE = os.path.join(LOG_DIR, 'ControlCenter.log')

def get_logger(name=None, log_file=LOG_FILE, level=logging.INFO):
    """Get a logger named for the module or class, with a rotating file handler."""
    if name is None:
        name = __name__
    
    # Use DEBUG level if advanced debugging is enabled
    global ADVANCED_DEBUG_MODE
    effective_level = logging.DEBUG if ADVANCED_DEBUG_MODE else level
    
    logger = logging.getLogger(name)
    logger.setLevel(effective_level)
    logger.propagate = False  # Prevent duplicate logs if root logger is configured
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # File handler (rotating)
    has_file_handler = any(isinstance(h, RotatingFileHandler) and h.baseFilename == os.path.abspath(log_file) for h in logger.handlers)
    if not has_file_handler:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5*1024*1024,
            backupCount=10
        )
        file_handler.setLevel(effective_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    # Stream handler (terminal)
    has_stream_handler = any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in logger.handlers)
    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)  # Show all levels in terminal
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    return logger

def delete_old_logs(logs_path=LOG_DIR, pattern='*.log', keep_last=5):
    """
    Deletes log files in the given directory that match the pattern, keeping only the specified number of most recent files.
    
    Args:
        logs_path (str): Directory containing log files
        pattern (str): Pattern to match log files (e.g., '*.log' or 'ControlCenter.log')
        keep_last (int): Number of most recent log files to keep
    """
    import glob
    # Get a list of log files in the directory
    log_files = sorted(
        glob.glob(os.path.join(logs_path, pattern)), 
        key=os.path.getmtime
    )
    
    # Delete the oldest log files if there are more than keep_last
    for log_file in log_files[:-keep_last]:
        try:
            os.remove(log_file)
        except OSError as e:
            print(f"Error deleting log file {log_file}: {e}")




# Function to log uncaught exceptions
def log_uncaught_exceptions(exc_type, exc_value, exc_traceback):
    """Handler for uncaught exceptions that logs them and shows an error message"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger = get_logger("uncaught_exception")
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    # You could add code here to show an error dialog to the user

sys.excepthook = log_uncaught_exceptions