IGNORED_PRINTER_ERRORS = [
    "Move out of range:"
]
# Critical printer errors that require immediate attention, can cancel the print using mainController.showPrinterError
CRITICAL_PRINTER_ERRORS = [
    "Can not update MCU", 
    "Error loading template", 
    "Must home axis first", 
    "probe",
    "Error during homing move", 
    "still triggered after retract", 
    "'mcu' must be specified", 
    "Unable to connect",
    "Shutdown due to M112",
    "Printer is not ready",
    "Unable to connect"
]
from collections import OrderedDict

# Configuration settings
ip = '0.0.0.0'
apiKey = 'B508534ED20348F090B4D0AD637D3660'   

# Screen resolution settings
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480

file_name = ''

filaments = [
    ("PLA", 190),
    ("ABS", 230),
    ("PETG", 230),
    ("PVA", 210),
    ("TPU", 220),
    ("Nylon", 270),
    ("PC", 270),
    ("HIPS", 220),
    ("WoodFill", 220),
    ("MetalFill", 215),
    ("ABS Carbon Fiber", 280),
    ("Nylon 12 Carbon Fiber", 280),
    ("PC Carbon Fiber", 300),
    
]

filaments = OrderedDict(filaments)

# Default/fallback printer configuration
# These values are used as fallback when Klipper configuration cannot be read
DEFAULT_CALIBRATION_POSITION = {'X1': 110, 'Y1': 18,
                                'X2': 510, 'Y2': 18,
                                'X3': 310, 'Y3': 308,
                                'X4': 310, 'Y4': 178
                                }

DEFAULT_MACHINE_BUILD_SIZE = {'X': 600, 'Y': 300, 'Z': 400}
DEFAULT_TOOL0_PURGE_POSITION = {'X': -30, 'Y': -77}
DEFAULT_TOOL1_PURGE_POSITION = {'X': 655, 'Y': -77}
DEFAULT_PTFE_TUBE_LENGTH = 1500  # 2400 for 600x600, 1500 for 600x300 keep as multiples of 300 only
DEFAULT_IS_DUAL_NOZZLE = True  # Set to False for single nozzle printers

# Dynamic printer configuration (loaded from Klipper at runtime)
# These will be populated by load_printer_config_from_klipper()
calibrationPosition = DEFAULT_CALIBRATION_POSITION.copy()
machineBuildSize = DEFAULT_MACHINE_BUILD_SIZE.copy() 
tool0PurgePosition = DEFAULT_TOOL0_PURGE_POSITION.copy()
tool1PurgePosition = DEFAULT_TOOL1_PURGE_POSITION.copy()
ptfeTubeLength = DEFAULT_PTFE_TUBE_LENGTH
IS_DUAL_NOZZLE = DEFAULT_IS_DUAL_NOZZLE


def load_printer_config_from_klipper():
    """
    Load printer configuration from Klipper PRINTER_VARIABLES.
    Updates the global configuration variables with values from the active printer.
    
    Returns:
        bool: True if configuration was successfully loaded, False if fallback values used
    """
    try:
        from utils.printer_config_manager import get_printer_config_from_klipper
        
        config = get_printer_config_from_klipper()
        if not config:
            return False
            
        global calibrationPosition, machineBuildSize, tool0PurgePosition
        global tool1PurgePosition, ptfeTubeLength, IS_DUAL_NOZZLE
        
        # Update global variables with extracted configuration
        if 'calibrationPosition' in config:
            calibrationPosition = config['calibrationPosition']
            
        if 'machineBuildSize' in config:
            machineBuildSize = config['machineBuildSize']
            
        if 'tool0PurgePosition' in config:
            tool0PurgePosition = config['tool0PurgePosition']
            
        if 'tool1PurgePosition' in config:
            tool1PurgePosition = config['tool1PurgePosition']
            
        if 'ptfeTubeLength' in config:
            ptfeTubeLength = config['ptfeTubeLength']
            
        if 'IS_DUAL_NOZZLE' in config:
            IS_DUAL_NOZZLE = config['IS_DUAL_NOZZLE']
            
        return True
        
    except Exception as e:
        # Log error but don't crash - use fallback values
        try:
            from utils.logger import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Failed to load printer configuration from Klipper, using defaults: {e}")
        except:
            print(f"Failed to load printer configuration from Klipper, using defaults: {e}")
        return False


def get_printer_config():
    """
    Get current printer configuration as a dictionary.
    
    Returns:
        dict: Current printer configuration values
    """
    return {
        'calibrationPosition': calibrationPosition,
        'machineBuildSize': machineBuildSize,
        'tool0PurgePosition': tool0PurgePosition,
        'tool1PurgePosition': tool1PurgePosition,
        'ptfeTubeLength': ptfeTubeLength,
        'IS_DUAL_NOZZLE': IS_DUAL_NOZZLE
    }