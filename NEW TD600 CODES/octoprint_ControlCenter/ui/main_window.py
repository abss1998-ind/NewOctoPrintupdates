import time

import requests
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QMessageBox, QSizePolicy
from ui.home_screen.home_screen import HomeScreen
from ui.loading_screen.loading_screen import LoadingScreen
from ui.menu_screen.menu_screen import MenuScreen
from ui.settings_screen.settings_screen import SettingsScreen
from ui.control_screen.control_screen import ControlScreen
from ui.print_from_location.print_from_location import PrintFromLocation
from ui.calibrate_screen.calibrate_screen import CalibrateScreen
from ui.filament_management_screen.filamentManagementScreen import filamentManagementScreen
from utils.logger import get_logger
import os
import subprocess
import ui.resources.resource_rc  # Ensure resources are loaded
import config
from utils.printer_ui_config import apply_nozzle_config_to_all_screens, is_dual_nozzle_printer
from utils.styles import printer_status_red, printer_status_green, printer_status_amber, printer_status_blue
# Import the specific dialog functions needed, not just the dialog module
from utils.dialog import WarningOk, WarningYesNo
import glob
from utils import dialog
from config import SCREEN_WIDTH, SCREEN_HEIGHT

class MainWindow(QMainWindow):
    def __init__(self, controller=None, printer_model=None):
        super(MainWindow, self).__init__()
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing MainWindow")

        # Flag to indicate if we're in minimal UI mode due to startup error
        self.minimalUI = False
        self.printer_model = printer_model
        self.controller = controller

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.central_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.central_widget.setLayout(self.layout)

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stacked_widget.setStyleSheet("background-color: rgb(40, 40, 40);")
        self.layout.addWidget(self.stacked_widget)

        # Screen navigation history for back button functionality
        self.screen_history = []
        self.current_screen = None

        # Next screen for wizard-style multi-step flows
        self.next_screen = None
        self.dialogShown = False
        self.setFixedSize(SCREEN_WIDTH, SCREEN_HEIGHT)  # Use config values for screen resolution
        

        self.loading_screen = LoadingScreen(self)
        self.stacked_widget.addWidget(self.loading_screen)
        self.show()
        self.logger.info("MainWindow initialized successfully, showing loading screen")



    def loadUI(self, minimalUI=False):
            """ Load the user interface screens based on the connection status.
            If minimal is True, load only the essential screens for minimal UI mode.
            """
            self.logger.info("Loading UI with minimal mode set to {}".format(minimalUI))
            self.minimalUI = minimalUI

            if minimalUI:
                self.logger.info("Showing minimal UI due to startup error")
                try:
                    self.octoprint_client = None
                    self.home_screen = HomeScreen(self,minimalUI=True)
                    self.stacked_widget.addWidget(self.home_screen)
                    self.logger.debug("Home screen loaded successfully")
                    self.menu_screen = MenuScreen(self,minimalUI=True)
                    self.stacked_widget.addWidget(self.menu_screen)
                    self.logger.debug("Menu screen loaded successfully")
                    self.settings_screen = SettingsScreen(self,minimalUI=True)
                    self.stacked_widget.addWidget(self.settings_screen)
                    self.logger.debug("Settings screen loaded successfully")
                    self.adjustSize()
                    self.logger.info("MainWindow initialized successfully")
                except Exception as e:
                    self.logger.exception("Error during MainWindow initialization")
                    WarningOk(self,
                            f"Application Error\n\nAn error occurred while initializing the application: {str(e)}\n\nPlease check the logs for more details.",
                            overlay=True)
                WarningOk(
                    self,
                    "Server Connection Error\n\nThe printer server is not reachable. Only basic features are available.\n\n"
                    "Please check your network connection and printer status.",
                    overlay=True
                )
                self.switch_to_home_screen()
            else:
                self.logger.info("Loading full UI - OctoPrint connection successful")
                try:
                    # Load all screens
                    self.octoprint_client = self.controller.octoprint_client
                    self.home_screen = HomeScreen(self, minimalUI=False)
                    self.stacked_widget.addWidget(self.home_screen)
                    self.logger.debug("Home screen loaded successfully")

                    self.menu_screen = MenuScreen(self, minimalUI=False)
                    self.stacked_widget.addWidget(self.menu_screen)
                    self.logger.debug("Menu screen loaded successfully")

                    self.settings_screen = SettingsScreen(self, minimalUI=False)
                    self.stacked_widget.addWidget(self.settings_screen)
                    self.logger.debug("Settings screen loaded successfully")

                    self.control_screen = ControlScreen(self)
                    self.stacked_widget.addWidget(self.control_screen)
                    self.logger.debug("Control screen loaded successfully")

                    self.print_location_screen = PrintFromLocation(self)
                    self.stacked_widget.addWidget(self.print_location_screen)
                    self.logger.debug("Print location screen loaded successfully")

                    self.calibrate_screen = CalibrateScreen(self)
                    self.stacked_widget.addWidget(self.calibrate_screen)
                    self.logger.debug("Calibrate screen loaded successfully")

                    self.filament_management_screen = filamentManagementScreen(self)
                    self.stacked_widget.addWidget(self.filament_management_screen)
                    self.logger.debug("Filament/Nozzle screen loaded successfully")

                    # Adjust the size of the main window to fit its contents
                    self.adjustSize()
                    self.logger.info("MainWindow initialized successfully")
                    
                    # Apply single/dual nozzle configuration
                    self._apply_nozzle_configuration()
                    
                except Exception as e:
                    self.logger.exception("Error during MainWindow initialization")
                    WarningOk(self,
                            f"Application Error\n\nAn error occurred while initializing the application: {str(e)}\n\nPlease check the logs for more details.",
                            overlay=True)
                self.switch_to_home_screen()
    

    # Screen Navigation Methods
    def switch_screen(self, widget):
        """Switch to the given screen and update navigation history."""
        self.logger.debug(f"Switching to screen: {widget.__class__.__name__}")
        self.logger.debug(
            f"Current screen before switch: {self.current_screen.__class__.__name__ if self.current_screen else None}")

        self.current_screen = widget
        self.stacked_widget.setCurrentWidget(widget)

    # Direct navigation methods for main screens
    def switch_to_home_screen(self):
        self.logger.debug("Switching to home screen")
        self.switch_screen(self.home_screen)

    def switch_to_menu_screen(self):
        self.logger.debug("Switching to menu screen")
        self.switch_screen(self.menu_screen)

    def switch_to_settings_screen(self):
        self.logger.debug("Switching to settings screen")
        self.switch_screen(self.settings_screen)

    def switch_to_control_screen(self):
        """
        Sets the current page to the control page
        """
        self.logger.debug("Switching to control screen")
        try:
            self.switch_screen(self.control_screen)
            # Spinbox values are now updated automatically via showEvent in control_screen
        except Exception as e:
            self.logger.error("Error in MainWindow.control: {}".format(e))
            dialog.WarningOk(self, "Error in MainWindow.control: {}".format(e), overlay=True)

    def switch_to_print_location_screen(self):
        self.logger.debug("Switching to print location screen")
        self.switch_screen(self.print_location_screen)

    def switch_to_calibrate_screen(self):
        self.logger.debug("Switching to calibration screen")
        #TBD: Send M502 to get latest values from printer
        self.switch_screen(self.calibrate_screen)

    def switch_to_filament_management_screen(self):
        self.logger.debug("Switching to filament/nozzle screen")
        self.switch_screen(self.filament_management_screen)
    
    def _apply_nozzle_configuration(self):
        """Apply single/dual nozzle configuration by hiding appropriate UI elements."""
        apply_nozzle_config_to_all_screens(self)
    
    def _hide_dual_nozzle_elements(self):
        """Hide all UI elements related to the second nozzle/tool when in single nozzle mode."""
        # This method is now handled by apply_nozzle_config_to_all_screens
        pass

