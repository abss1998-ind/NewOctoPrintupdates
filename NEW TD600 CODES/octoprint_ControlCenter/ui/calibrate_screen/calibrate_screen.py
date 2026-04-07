import os
from PyQt5.QtWidgets import QWidget, QToolButton, QPushButton, QStackedWidget
from PyQt5 import uic
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils.printer_ui_config import apply_nozzle_config_to_screen
from utils import dialog

# Import all calibration sub-screens
from ui.calibrate_screen.nozzleOffsetPage.nozzleOffsetPage import NozzleOffsetPage
from ui.calibrate_screen.toolOffset.toolOffset import ToolOffset
from ui.calibrate_screen.bedLevelingPage.bedLevelingPage import BedLeveling
from ui.calibrate_screen.idexLevelCalibration.idexLevelCalibration import IdexLevelCalibration
from ui.calibrate_screen.cameraToolOffsetCalibration.cameraToolOffsetCalibration import CameraToolOffsetCalibration
from ui.calibrate_screen.ZtoolOffsetWizard.ZtoolOffsetWizard import ZtoolOffsetWizard
from ui.calibrate_screen.ZProbeOffsetWizard.ZProbeOffsetWizard import ZProbeOffsetWizard


logger = get_logger(__name__)

class CalibrateScreen(QWidget):
    def __init__(self, main_window):
        super(CalibrateScreen, self).__init__()
        self.main_window = main_window
        self.octoprint_client = main_window.octoprint_client
        self.logger = get_logger(self.__class__.__name__)

        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "calibrate_screen.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("CalibrateScreen UI loaded successfully")
        except Exception as e:
            self.logger.exception(f"Failed to load CalibrateScreen UI file: {e}")

        # Initialize UI components
        self.calibration_stacked_widget = self.findChild(QStackedWidget, "mainCalibrateStackedWidget")
        self.main_calibrate_page = self.findChild(QWidget, "mainCalibratePage")
        self.calibrationWizardButton = self.findChild(QToolButton, "calibrationWizardButton")
        self.inputShaperCalibrateButton = self.findChild(QToolButton, "inputShaperCalibrateButton")
        self.cameraToolOffsetCalibrateButton = self.findChild(QToolButton, "cameraToolOffsetCalibrateButton")
        self.nozzleOffsetButton = self.findChild(QToolButton, "nozzleOffsetButton")
        self.toolOffsetZButton = self.findChild(QToolButton, "toolOffsetZButton")
        self.toolOffsetXYButton = self.findChild(QToolButton, "toolOffsetXYButton")
        self.idexCalibrationWizardButton = self.findChild(QToolButton, "idexCalibrationWizardButton")
        self.toolZOffsetWizardButton = self.findChild(QToolButton, "ToolZOffsetWizardButton")
        self.zProbeOffsetWizardButton = self.findChild(QToolButton, "zProbeOffsetWizardButton")

        self.calibrateBackButton = self.findChild(QPushButton, "calibrateBackButton")

        # Validate UI components
        check_ui_elements(self, [
            self.calibration_stacked_widget, self.main_calibrate_page,
            self.calibrationWizardButton, self.inputShaperCalibrateButton,
            self.cameraToolOffsetCalibrateButton, self.nozzleOffsetButton, self.toolOffsetZButton, self.toolOffsetXYButton, self.idexCalibrationWizardButton,
            self.toolZOffsetWizardButton, self.zProbeOffsetWizardButton, self.calibrateBackButton
        ], "CalibrateScreen")

        # Initialize all sub-screens
        self.screens = {}
        self._initialize_sub_screens()

        # Connect buttons to their respective methods
        self.calibrationWizardButton.clicked.connect(lambda: self.show_calibrate_screen("bed_leveling"))
        self.inputShaperCalibrateButton.clicked.connect(self.inputShaperCalibrate)
        self.cameraToolOffsetCalibrateButton.clicked.connect(lambda: self.show_calibrate_screen("camera_tool_offset"))
        self.nozzleOffsetButton.clicked.connect(lambda: self.show_calibrate_screen("nozzle_offset"))
        self.toolOffsetZButton.clicked.connect(lambda: self.show_calibrate_screen("tool_offset", tab="Z"))
        self.toolOffsetXYButton.clicked.connect(lambda: self.show_calibrate_screen("tool_offset", tab="XY"))
        self.idexCalibrationWizardButton.clicked.connect(lambda: self.show_calibrate_screen("idex_calibration"))
        if self.toolZOffsetWizardButton:
            self.toolZOffsetWizardButton.clicked.connect(lambda: self.show_calibrate_screen("z_tool_offset"))
        if self.zProbeOffsetWizardButton:
            self.zProbeOffsetWizardButton.clicked.connect(lambda: self.show_calibrate_screen("z_probe_offset"))
        self.calibrateBackButton.clicked.connect(lambda: self.main_window.switch_to_menu_screen())

        # Show the main calibration page initially
        self.calibration_stacked_widget.setCurrentWidget(self.main_calibrate_page)
        self.logger.debug("Set current widget to mainCalibratePage")

        # Apply nozzle configuration
        self.apply_nozzle_configuration()

        # Connect to Klipper state changes to disable buttons when not ready
        self.main_window.printer_model.klipper_state_changed.connect(self.on_klipper_state_changed)
        self.logger.debug("Connected CalibrateScreen to Klipper state updates")
        
        # Initialize Klipper state UI
        try:
            current_klipper_state = getattr(self.main_window.printer_model, 'klipper_state', 'unknown')
            self.on_klipper_state_changed(current_klipper_state)
        except Exception as e:
            self.logger.debug(f"Could not initialize Klipper state UI: {e}")

    def apply_nozzle_configuration(self):
        """Hide dual nozzle elements for single nozzle configuration."""
        apply_nozzle_config_to_screen(self, 'calibrate_screen')

    def showEvent(self, event):
        """Reset to main_calibrate_page whenever this widget is shown from main window navigation."""
        super().showEvent(event)
        try:
            self.calibration_stacked_widget.setCurrentWidget(self.main_calibrate_page)
            self.logger.debug("Reset stacked widget to main_calibrate_page on show")
        except Exception as e:
            self.logger.error(f"Error resetting to main_calibrate_page: {e}")

    def _initialize_sub_screens(self):
        """Initialize all calibration sub-screens"""
        try:
            # Create instances of each sub-screen
            self.screens["bed_leveling"] = BedLeveling(self.main_window)
            self.screens["nozzle_offset"] = NozzleOffsetPage(self.main_window)
            self.screens["tool_offset"] = ToolOffset(self.main_window)
            self.screens["camera_tool_offset"] = CameraToolOffsetCalibration(self.main_window)
            self.screens["idex_calibration"] = IdexLevelCalibration(self.main_window)
            self.screens["z_tool_offset"] = ZtoolOffsetWizard(self.main_window)
            self.screens["z_probe_offset"] = ZProbeOffsetWizard(self.main_window)

            # Add each screen to the stacked widget
            for name, screen in self.screens.items():
                self.calibration_stacked_widget.addWidget(screen)
                self.logger.info(f"Added {name} screen to calibration stacked widget")
        except Exception as e:
            self.logger.exception(f"Error initializing sub-screens: {e}")

    def inputShaperCalibrate(self):
        self.logger.info("CalibrateScreen.inputShaperCalibrate started")
        try:
            dialog.WarningOk(self, "Wait for all calibration movements to finish before proceeding.", overlay=True)
            self.octoprint_client.gcode(command='G28')
            self.octoprint_client.gcode(command='SHAPER_CALIBRATE')
            self.octoprint_client.gcode(command='SAVE_CONFIG')

        except Exception as e:
            error_message = f"Error in inptuShaperCalibrate: {str(e)}"
            self.logger.error(error_message)
            dialog.WarningOk(error_message, overlay=True)

    def show_calibrate_screen(self, target_screen=None, tab=None):
        """Show a specific calibration screen or the main calibration page.

        Args:
            target_screen: Optional string identifying which sub-screen to navigate to.
                           None means show the main calibration page.
            tab: Optional sub-view selector. For 'tool_offset', accepts 'Z' or 'XY'.
        """
        self.logger.debug(f"show_calibrate_screen called with target_screen={target_screen}, tab={tab}")

        # Only switch to this screen in the main window if we're not already on it
        if self.main_window.current_screen != self:
            self.main_window.switch_screen(self)

        # If no specific target is requested, show the main calibration page
        if not target_screen:
            self.calibration_stacked_widget.setCurrentWidget(self.main_calibrate_page)
            self.logger.debug("Showing main calibration page")
            return

        # Refresh tool/nozzle offsets when entering related screens
        self.octoprint_client.gcode(command='M503')


        # Check if the requested screen exists
        if target_screen not in self.screens:
            self.logger.error(f"Requested screen '{target_screen}' not found in available screens")
            return

        # Navigate to the requested sub-screen
        screen = self.screens[target_screen]
        self.calibration_stacked_widget.setCurrentWidget(screen)
        self.logger.info(f"Navigated to {target_screen}")

        # Handle sub-view/tab selection for tool_offset
        if target_screen == "tool_offset" and tab:
            try:
                if tab == "Z" and hasattr(screen, "toolOffsetZPage"):
                    screen.stackedWidget.setCurrentWidget(screen.toolOffsetZPage)
                    self.logger.debug("Showing Tool Offset Z tab via show_calibrate_screen")
                elif tab == "XY" and hasattr(screen, "toolOffsetXYPage"):
                    screen.stackedWidget.setCurrentWidget(screen.toolOffsetXYPage)
                    self.logger.debug("Showing Tool Offset XY tab via show_calibrate_screen")
                else:
                    self.logger.warning(f"Unrecognized or unavailable tab '{tab}' for tool_offset")
            except Exception as e:
                self.logger.error(f"Error setting tool_offset tab '{tab}': {e}")

    def on_klipper_state_changed(self, state):
        """Disable all calibration buttons except back button when Klipper is not ready"""
        try:
            state_lower = str(state).strip().lower()
            # Accept multiple states as "ready": ready, operational, idle
            # Also allow unknown state to keep buttons enabled (temporary for debugging)
            is_ready = state_lower in ['ready', 'operational', 'idle', 'unknown']
            self.logger.info(f"CalibrateScreen: Klipper state changed to: '{state}' (normalized: '{state_lower}'), is_ready: {is_ready}")
            
            # List all calibration buttons that should be disabled when Klipper is not ready
            # Keep the back button always enabled
            calibration_buttons = [
                self.calibrationWizardButton,
                self.inputShaperCalibrateButton, 
                self.cameraToolOffsetCalibrateButton,
                self.nozzleOffsetButton,
                self.toolOffsetZButton,
                self.toolOffsetXYButton,
                self.idexCalibrationWizardButton,
                self.toolZOffsetWizardButton,
                self.zProbeOffsetWizardButton
            ]
            
            # Enable/disable calibration buttons based on Klipper state
            for button in calibration_buttons:
                if button:  # Check if button exists (some may be None)
                    button.setEnabled(is_ready)
                    
        except Exception as e:
            self.logger.error(f"Error updating CalibrateScreen UI for Klipper state {state}: {e}")
