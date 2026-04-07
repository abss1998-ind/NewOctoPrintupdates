"""
Printer UI Configuration Module

This module handles printer configuration (single vs dual nozzle) and manages
which UI elements should be shown/hidden based on the printer type.
"""

import config
from utils.logger import get_logger

logger = get_logger(__name__)

def is_dual_nozzle_printer():
    """Check if the printer is configured for dual nozzle operation."""
    # Access the current value dynamically to pick up changes from Klipper config loading
    return config.IS_DUAL_NOZZLE

# UI elements that should be hidden for single nozzle printers
DUAL_NOZZLE_ELEMENTS = {
    'home_screen': [
        'tool1Layout', 'tool1Label', 'tool1LoadedNozzle', 'tool1LoadedFilament',
        'tool1TargetTemperature', 'tool1TempBar', 'tool1ActualTemperature', 'tool1TextLabel', 'toolSeperationLine'
    ],
    'control_screen': [
        'toolToggleTemperatureButton', 'toolToggleMotionButton'
    ],
    'filament_management_screen': [
        'changeTool1MaterialBayX', 'tool1Frame', 'editTool1MaterialBayX',
        'tool11MaterialBayXStateColor', 'tool1MaterialBayXStateLabel', 'changeTool1Button',
        'tool1MaterialBayXLabel'
    ],
    'calibrate_screen': [
        'idexCalibrationWizardButton', 'toolOffsetZButton', 'toolOffsetXYButton',
        'cameraToolOffsetCalibrateButton', 'toolZOffsetWizardButton'
    ]
}

def hide_dual_nozzle_elements(widget, element_names):
    """
    Hide specified UI elements if printer is configured for single nozzle.
    
    Args:
        widget: The parent widget containing the elements
        element_names: List of element names to hide for single nozzle printers
    """
    if not is_dual_nozzle_printer():
        for element_name in element_names:
            element = getattr(widget, element_name, None)
            if element:
                try:
                    element.hide()
                    logger.debug(f"Hidden dual nozzle element: {element_name}")
                except Exception as e:
                    logger.error(f"Error hiding element {element_name}: {e}")

def force_single_tool(requested_tool):
    """
    Force tool1 requests to tool0 for single nozzle printers.
    
    Args:
        requested_tool: The requested tool ("tool0" or "tool1")
        
    Returns:
        str: "tool0" for single nozzle printers, original tool for dual nozzle
    """
    if requested_tool == "tool1" and not is_dual_nozzle_printer():
        logger.info("Forced tool1 to tool0 for single nozzle configuration")
        return "tool0"
    return requested_tool

def get_dual_nozzle_elements(screen_name):
    """
    Get the list of dual nozzle elements for a specific screen.
    
    Args:
        screen_name: Name of the screen (e.g., 'home_screen', 'control_screen')
        
    Returns:
        list: List of element names to hide for single nozzle printers
    """
    return DUAL_NOZZLE_ELEMENTS.get(screen_name, [])

def apply_nozzle_config_to_screen(widget, screen_name):
    """
    Apply nozzle configuration to a specific screen widget.
    
    Args:
        widget: The screen widget
        screen_name: Name of the screen for element lookup
    """
    hide_dual_nozzle_elements(widget, get_dual_nozzle_elements(screen_name))

def apply_nozzle_config_to_all_screens(main_window):
    """
    Apply nozzle configuration to all screens in the main window.
    
    Args:
        main_window: The main window containing all screen widgets
    """
    if not is_dual_nozzle_printer():
        try:
            for screen_name, elements in DUAL_NOZZLE_ELEMENTS.items():
                if hasattr(main_window, screen_name):
                    screen = getattr(main_window, screen_name)
                    hide_dual_nozzle_elements(screen, elements)
                    
            logger.info("Successfully applied single nozzle configuration to all screens")
        except Exception as e:
            logger.error(f"Error applying nozzle configuration: {e}")
    else:
        logger.info("Dual nozzle configuration active - all elements visible")
