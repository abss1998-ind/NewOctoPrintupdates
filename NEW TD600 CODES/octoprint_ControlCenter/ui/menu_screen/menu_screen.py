"""Menu screen module for OctoPrint Control Center.

This module provides the main navigation menu interface allowing users to
access different application screens including print, control, calibrate,
filament/nozzle management, and settings.
"""
import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QToolButton, QPushButton
from utils.helpers import check_ui_elements
from utils.logger import get_logger


class MenuScreen(QWidget):
    """Main navigation menu screen widget.
    
    Provides navigation buttons to access different application screens
    including print management, control panel, calibration, filament/nozzle
    settings, and application settings.
    """
    
    def __init__(self, main_window, minimalUI=False):
        """Initialize the menu screen.
        
        Args:
            main_window: Reference to the main application window.
            minimalUI: Whether to enable minimal UI mode with limited functionality.
        """
        super(MenuScreen, self).__init__()
        self.main_window = main_window
        self.minimalUI = minimalUI

        # Use centralized logger
        self.logger = get_logger(self.__class__.__name__)

        # Load the UI with proper error handling
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "menu_screen.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("MenuScreen UI loaded successfully")
        except Exception as e:
            self.logger.exception(f"Failed to load MenuScreen UI file: {e}")
            raise RuntimeError(f"Cannot initialize MenuScreen: UI file loading failed - {e}")
            
        # Initialize UI components
        # Navigation tool buttons
        self.menuPrintButton = self.findChild(QToolButton, "menuPrintButton")
        self.menuControlButton = self.findChild(QToolButton, "menuControlButton")
        self.menuCalibrateButton = self.findChild(QToolButton, "menuCalibrateButton")
        self.menuFilamentNozzleButton = self.findChild(QToolButton, "menuFilamentNozzleButton")
        self.menuSettingsButton = self.findChild(QToolButton, "menuSettingsButton")
        
        # Basic navigation buttons
        self.menuBackButton = self.findChild(QPushButton, "menuBackButton")
        
        # Validate UI components with the simplified check_ui_elements function
        all_ui_elements = [
            self.menuPrintButton,
            self.menuControlButton, 
            self.menuCalibrateButton,
            self.menuFilamentNozzleButton,
            self.menuSettingsButton,
            self.menuBackButton
        ]
        check_ui_elements(self, all_ui_elements, "MenuScreen")
        
        # Connect buttons to their respective screens using lambda functions
        self.menuPrintButton.clicked.connect(lambda: self.main_window.switch_to_print_location_screen())
        self.menuControlButton.clicked.connect(lambda: self.main_window.switch_to_control_screen())
        self.menuCalibrateButton.clicked.connect(lambda: self.main_window.switch_to_calibrate_screen())
        self.menuFilamentNozzleButton.clicked.connect(lambda: self.main_window.switch_to_filament_management_screen())
        self.menuSettingsButton.clicked.connect(lambda: self.main_window.switch_to_settings_screen())
        self.menuBackButton.clicked.connect(lambda: self.main_window.switch_to_home_screen())

        if self.minimalUI:
             # Disable buttons in Menu Screen
            self.menuControlButton.setEnabled(False)
            self.menuPrintButton.setEnabled(False)
            self.menuCalibrateButton.setEnabled(False)
            self.menuFilamentNozzleButton.setEnabled(False)
        else:
            # Enable buttons in Menu Screen
            self.menuControlButton.setEnabled(True)
            self.menuPrintButton.setEnabled(True)
            self.menuCalibrateButton.setEnabled(True)
            self.menuFilamentNozzleButton.setEnabled(True)
            self.main_window.printer_model.status_updated.connect(self.buttonStatusUpdate)

    def buttonStatusUpdate(self, status):
        """Update MenuScreen UI elements based on printer status"""
        try:
            # Disable certain menu options during printing
            if status in ["Printing", "Paused"]:
                self.menuCalibrateButton.setDisabled(True)
                self.menuPrintButton.setDisabled(True)
            else:  # Offline, Operational, etc.
                self.menuCalibrateButton.setDisabled(False)
                self.menuPrintButton.setDisabled(False)
        except Exception as e:
            self.logger.error(f"Error updating MenuScreen UI for status {status}: {e}")