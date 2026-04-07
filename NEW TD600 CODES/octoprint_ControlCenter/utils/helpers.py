from utils.logger import get_logger
import subprocess
import re
from threading import Thread
from functools import wraps


def format_printer_status(status):
    """Format the printer status for display."""
    return f"Status: {status['state']['text']}, Progress: {status['progress']['completion']}%"

def handle_api_error(error):
    """Handle errors from the OctoPrint API."""
    logger = get_logger(__name__)
    logger.error(f"API Error: {error}")

def validate_ip_address(ip):
    """Validate the format of an IP address."""
    import re
    pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
    return re.match(pattern, ip) is not None

def convert_to_percentage(value, total):
    """Convert a value to a percentage of a total."""
    if total == 0:
        return 0
    return (value / total) * 100

def check_ui_elements(ui_class, elements_list, screen_name):
    """
    Check if UI elements exist and log warnings for missing ones.

    Args:
        ui_class: The class instance containing the UI elements
        elements_list: List of UI element objects
        screen_name: Name of the screen for logging purposes
    """
    logger = get_logger(__name__)
    missing_elements = []
    
    for element in elements_list:
        if element is None:
            # Try to find the element's name from ui_class's attributes
            element_name = "Unknown"
            for attr_name, attr_value in vars(ui_class).items():
                if attr_value is None and not attr_name.startswith('_'):
                    element_name = attr_name
                    break
            missing_elements.append(element_name)
    
    if missing_elements:
        logger.warning(f"Missing UI elements in {screen_name}: {len(missing_elements)}")
        for element in missing_elements:
            logger.warning(f"  - {element}")
    else:
        pass
        # my_logger.info(f"All UI elements validated successfully for {screen_name}")

def run_async(func):
    """
    Function decorator to make methods run in a thread
    """
    @wraps(func)
    def async_func(*args, **kwargs):
        func_hl = Thread(target=func, args=args, kwargs=kwargs)
        func_hl.start()
        return func_hl

    return async_func

