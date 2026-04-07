import time

import os
from PyQt5 import uic
from PyQt5 import QtGui, QtCore
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import QWidget, QPushButton, QSpinBox, QTabWidget, QToolButton
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils.printer_ui_config import apply_nozzle_config_to_screen, is_dual_nozzle_printer
from utils import dialog

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s


logger = get_logger(__name__)

class ControlScreen(QWidget):
    def __init__(self, main_window):
        super(ControlScreen, self).__init__()
        self.main_window = main_window
        self.octoprint_client = main_window.octoprint_client

        # Use centralized logger
        self.logger = get_logger(self.__class__.__name__)

        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "control_screen.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("ControlScreen UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load ControlScreen UI file: {e}", exc_info=True)

        # Initialize UI components
        self.controlTabWidget = self.findChild(QTabWidget, "controlTabWidget")
        self.controlBackButton = self.findChild(QPushButton, "controlBackButton")

        # Tab widgets
        self.tuneTab = self.findChild(QWidget, "tuneTab")
        self.temperatureTab = self.findChild(QWidget, "temperatureTab")
        self.motionTab = self.findChild(QWidget, "motionTab")
        self.preferencesTab = self.findChild(QWidget, "preferencesTab")

        # Feed rate controls (now in tuneTab)
        self.feedRateSpinBox = self.findChild(QSpinBox, "feedRateSpinBox")
        self.setFeedRateButton = self.findChild(QPushButton, "setFeedRateButton")
        self.moveZPBabyStep = self.findChild(QPushButton, "moveZPBabyStep")
        self.moveZMBabyStep = self.findChild(QPushButton, "moveZMBabyStep")

        # Flow rate controls (now in tuneTab)
        self.flowRateSpinBox = self.findChild(QSpinBox, "flowRateSpinBox")
        self.setFlowRateButton = self.findChild(QPushButton, "setFlowRateButton")

        # Preferences controls
        self.toggleFilamentRunoutButton = self.findChild(QPushButton, "toggleFilamentRunoutButton")
        self.toggleFilamentJamButton = self.findChild(QPushButton, "toggleFilamentJamButton")
        self.toggleAutoResumeButton = self.findChild(QPushButton, "toggleAutoResumeButton")
        self.toggleCheckPrintCompatibilityButton = self.findChild(QPushButton, "toggleCheckPrintCompatibilityButton")
        self.togglePrintRestoreButton = self.findChild(QPushButton, "togglePrintRestoreButton")
        self.toggleFirmwareUpdateButton = self.findChild(QPushButton, "toggleFirmwareUpdateButton")
        self.advaceDebuggingModeButton = self.findChild(QPushButton, "advaceDebuggingModeButton")

        # Temperature controls
        self.fanOnButton = self.findChild(QPushButton, "fanOnButton")
        self.fanOffButton = self.findChild(QPushButton, "fanOffButton")
        self.cooldownButton = self.findChild(QPushButton, "cooldownButton")
        self.toolTempSpinBox = self.findChild(QSpinBox, "toolTempSpinBox")
        self.setToolTempButton = self.findChild(QPushButton, "setToolTempButton")
        self.bedTempSpinBox = self.findChild(QSpinBox, "bedTempSpinBox")
        self.setBedTempButton = self.findChild(QPushButton, "setBedTempButton")
        self.toolToggleTemperatureButton = self.findChild(QPushButton, "toolToggleTemperatureButton")
        self.tool180PreheatButton = self.findChild(QPushButton, "tool180PreheatButton")
        self.tool250PreheatButton = self.findChild(QPushButton, "tool250PreheatButton")
        self.bed60PreheatButton = self.findChild(QPushButton, "bed60PreheatButton")
        self.bed100PreheatButton = self.findChild(QPushButton, "bed100PreheatButton")

        # Motion controls
        self.step1mmButton = self.findChild(QPushButton, "step1mmButton")
        self.step10mmButton = self.findChild(QPushButton, "step10mmButton")
        self.step100mmButton = self.findChild(QPushButton, "step100mmButton")
        self.moveXPButton = self.findChild(QPushButton, "moveXPButton")
        self.moveXMButton = self.findChild(QPushButton, "moveXMButton")
        self.moveYPButton = self.findChild(QPushButton, "moveYPButton")
        self.moveYMButton = self.findChild(QPushButton, "moveYMButton")
        self.motorOffButton = self.findChild(QPushButton, "motorOffButton")
        self.homeXYButton = self.findChild(QPushButton, "homeXYButton")
        self.moveZMButton = self.findChild(QPushButton, "moveZMButton")
        self.moveZPButton = self.findChild(QPushButton, "moveZPButton")
        self.homeZButton = self.findChild(QPushButton, "homeZButton")
        self.toolToggleMotionButton = self.findChild(QPushButton, "toolToggleMotionButton")
        self.extruderButton = self.findChild(QPushButton, "extruderButton")
        self.retractButton = self.findChild(QPushButton, "retractButton")


        # Validate UI components
        required_components = [
            self.controlTabWidget, self.controlBackButton, self.feedRateSpinBox,
            self.setFeedRateButton, self.moveZPBabyStep, self.moveZMBabyStep,
            self.fanOnButton, self.fanOffButton, self.cooldownButton,
            self.toolTempSpinBox, self.setToolTempButton, self.bedTempSpinBox,
            self.setBedTempButton, self.step1mmButton, self.step10mmButton,
            self.step100mmButton, self.moveXPButton, self.moveXMButton,
            self.moveYPButton, self.moveYMButton, self.flowRateSpinBox,
            self.setFlowRateButton, 
            self.tuneTab, self.temperatureTab, self.motionTab, self.preferencesTab,
            self.toggleFilamentRunoutButton, self.toggleFilamentJamButton,
            self.toggleAutoResumeButton, self.toggleCheckPrintCompatibilityButton,
            self.togglePrintRestoreButton
        ]
        
        # Add firmware update check button if it exists (optional for backward compatibility)
        if self.toggleFirmwareUpdateButton:
            required_components.append(self.toggleFirmwareUpdateButton)
            
        # Add advanced debugging button if it exists (optional for backward compatibility) 
        if self.advaceDebuggingModeButton:
            required_components.append(self.advaceDebuggingModeButton)
            
        check_ui_elements(self, required_components, "ControlScreen")

        # Apply scrollbar styling - find and style all scroll areas
        self.apply_scrollbar_styling()

        # set the active extruder to 0 initially
        self.setActiveExtruder(0)  # Default to extruder 0

        # Feed Rate Buttons Signal Connections
        self.controlBackButton.clicked.connect(lambda: self.main_window.switch_to_home_screen())
        self.setFeedRateButton.clicked.connect(self.setFeedRate)
        self.moveZPBabyStep.clicked.connect(
            lambda: self.octoprint_client.gcode(command='M290 Z0.025')
        )
        self.moveZMBabyStep.clicked.connect(
            lambda: self.octoprint_client.gcode(command='M290 Z-0.025')
        )

        # Temperature Buttons Signal Connections
        self.fanOnButton.clicked.connect(lambda: self.octoprint_client.gcode(command='M106 S255'))
        self.fanOffButton.clicked.connect(lambda: self.octoprint_client.gcode(command='M107'))
        self.cooldownButton.clicked.connect(self.coolDownAction)
        self.setToolTempButton.clicked.connect(self.setToolTemp)
        self.setBedTempButton.clicked.connect(lambda: self.octoprint_client.setBedTemperature(self.bedTempSpinBox.value()))
        self.bed60PreheatButton.clicked.connect(lambda: self.preheatBedTemp(60))
        self.bed100PreheatButton.clicked.connect(lambda: self.preheatBedTemp(100))
        self.tool180PreheatButton.clicked.connect(lambda: self.preheatToolTemp(180))
        self.tool250PreheatButton.clicked.connect(lambda: self.preheatToolTemp(250))
        self.toolToggleTemperatureButton.clicked.connect(self.selectToolTemperature)

        # Motion Buttons Signal Connections
        self.step1mmButton.clicked.connect(lambda: self.setStep(1))
        self.step10mmButton.clicked.connect(lambda: self.setStep(10))
        self.step100mmButton.clicked.connect(lambda: self.setStep(100))
        self.moveXPButton.clicked.connect(lambda: self.octoprint_client.jog(x=self.step, speed=2000))
        self.moveXMButton.clicked.connect(lambda: self.octoprint_client.jog(x=-self.step, speed=2000))
        self.moveYPButton.clicked.connect(lambda: self.octoprint_client.jog(y=self.step, speed=2000))
        self.moveYMButton.clicked.connect(lambda: self.octoprint_client.jog(y=-self.step, speed=2000))
        self.motorOffButton.clicked.connect(lambda: self.octoprint_client.gcode(command='M18'))
        self.homeXYButton.clicked.connect(self.homeXYAndSync)
        self.moveZMButton.clicked.connect(lambda: self.octoprint_client.jog(z=-self.step, speed=2000))
        self.moveZPButton.clicked.connect(lambda: self.octoprint_client.jog(z=self.step, speed=2000))
        self.homeZButton.clicked.connect(self.homeZAndSync)
        self.toolToggleMotionButton.clicked.connect(self.selectToolMotion)
        self.extruderButton.clicked.connect(lambda: self.octoprint_client.extrude(self.step))
        self.retractButton.clicked.connect(lambda: self.octoprint_client.extrude(-self.step))

        # Filament Buttons Signal Connections
        self.setFlowRateButton.clicked.connect(self.setFlowRate)

        self.toggleFilamentRunoutButton.clicked.connect(self.toggleFilamentRunout)

        self.toggleFilamentJamButton.clicked.connect(self.toggleFilamentJam)

        # Preferences Signal Connections
        self.toggleAutoResumeButton.clicked.connect(self.toggleAutoResume)
        self.toggleCheckPrintCompatibilityButton.clicked.connect(self.toggleCheckPrintCompatibility)
        self.togglePrintRestoreButton.clicked.connect(self.togglePrintRestore)
        if self.toggleFirmwareUpdateButton:
            self.toggleFirmwareUpdateButton.clicked.connect(self.toggleFirmwareUpdate)
        if self.advaceDebuggingModeButton:
            self.advaceDebuggingModeButton.clicked.connect(self.toggleAdvancedDebugging)

        # Configure spinboxes
        for spinbox in [self.feedRateSpinBox, self.toolTempSpinBox, self.bedTempSpinBox, self.flowRateSpinBox]:
            if spinbox:
                spinbox.lineEdit().setReadOnly(True)
                # spinbox.lineEdit().setDisabled(True)
                # Prevent text selection/highlighting by disabling focus
                spinbox.setFocusPolicy(QtCore.Qt.NoFocus)
                spinbox.lineEdit().setFocusPolicy(QtCore.Qt.NoFocus)
                # Make the highlight color match the background
                palette = QPalette()
                palette.setColor(QPalette.Highlight, QColor(255, 255, 255))
                palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
                spinbox.lineEdit().setPalette(palette)

        self.setStep(1)

        # Reflect persistent filament sensor preferences in toggle buttons
        try:
            runout_enabled = bool(self.main_window.printer_model.filament_runout_sensor_persistent_state)
            self.toggleFilamentRunoutButton.setChecked(runout_enabled)
            jam_enabled = bool(self.main_window.printer_model.filament_jam_sensor_persistent_state)
            self.toggleFilamentJamButton.setChecked(jam_enabled)
            # Initialize print compatibility check button
            compatibility_enabled = bool(self.main_window.printer_model.print_compatibility_check_enabled)
            self.toggleCheckPrintCompatibilityButton.setChecked(compatibility_enabled)
            # Initialize print restore preferences
            print_restore_enabled = bool(self.main_window.printer_model.print_restore_enabled)
            self.togglePrintRestoreButton.setChecked(print_restore_enabled)
            auto_resume_enabled = bool(self.main_window.printer_model.auto_resume_enabled)
            self.toggleAutoResumeButton.setChecked(auto_resume_enabled)
            # Initialize firmware update check preference
            firmware_update_check_enabled = bool(self.main_window.printer_model.firmware_update_check_enabled)
            if self.toggleFirmwareUpdateButton:
                self.toggleFirmwareUpdateButton.setChecked(firmware_update_check_enabled)
            # Initialize advanced debugging mode preference
            advanced_debugging_enabled = bool(self.main_window.printer_model.advanced_debugging_enabled)
            if self.advaceDebuggingModeButton:
                self.advaceDebuggingModeButton.setChecked(advanced_debugging_enabled)
            # Set auto resume button state based on print restore being enabled
            self.toggleAutoResumeButton.setEnabled(print_restore_enabled)
        except Exception as e:
            self.logger.warning(f"Failed initializing toggle buttons: {e}")


        # Connect to printer model for status updates
        self.main_window.printer_model.status_updated.connect(self.buttonStatusUpdate)
        self.main_window.printer_model.active_extruder_changed.connect(self.setActiveExtruder)
        # Connect to Klipper state changes to disable buttons when not ready
        self.main_window.printer_model.klipper_state_changed.connect(self.on_klipper_state_changed)
        self.logger.debug("Connected ControlScreen to printer model status updates")
        
        # Initialize Klipper state UI
        try:
            current_klipper_state = getattr(self.main_window.printer_model, 'klipper_state', 'unknown')
            self.on_klipper_state_changed(current_klipper_state)
        except Exception as e:
            self.logger.debug(f"Could not initialize Klipper state UI: {e}")

        # Initialize spinboxes with current values from printer model
        try:
            if hasattr(self.main_window.printer_model, 'current_feed_rate'):
                self.feedRateSpinBox.setValue(self.main_window.printer_model.current_feed_rate)
            if hasattr(self.main_window.printer_model, 'current_flow_rate'):
                self.flowRateSpinBox.setValue(self.main_window.printer_model.current_flow_rate)
        except Exception as e:
            self.logger.debug(f"Could not initialize spinboxes from model: {e}")

        # Apply nozzle configuration
        self.apply_nozzle_configuration()

    def showEvent(self, event):
        """Update all spinbox values with latest printer model data when screen is shown."""
        super().showEvent(event)
        self.update_spinbox_values()

    def update_spinbox_values(self):
        """Update all spinbox values with the latest data from printer model."""
        try:
            # Update feed rate and flow rate
            if hasattr(self.main_window.printer_model, 'current_feed_rate'):
                self.feedRateSpinBox.setValue(self.main_window.printer_model.current_feed_rate)
            if hasattr(self.main_window.printer_model, 'current_flow_rate'):
                self.flowRateSpinBox.setValue(self.main_window.printer_model.current_flow_rate)
            
            # Update bed temperature (always use bed target)
            bed_target = self.main_window.printer_model.temperatures.get('bedTarget', 0)
            self.bedTempSpinBox.setValue(bed_target)
            
            # Update tool temperature based on active tool and nozzle configuration
            if is_dual_nozzle_printer():
                # For dual nozzle, sync temperature toggle with active extruder
                active_extruder = getattr(self.main_window.printer_model, 'active_extruder', 0)
                if hasattr(self, 'toolToggleTemperatureButton'):
                    self.toolToggleTemperatureButton.setChecked(active_extruder == 1)
            
            # Update tool temperature spinbox using helper method
            self._update_tool_temperature_spinbox()
            
        except Exception as e:
            self.logger.error(f"Error updating spinbox values: {e}")

    def apply_nozzle_configuration(self):
        """Hide dual nozzle elements and apply styling for single nozzle configuration."""
        apply_nozzle_config_to_screen(self, 'control_screen')
        
        # Apply border radius styling for single nozzle mode
        if not is_dual_nozzle_printer():
            self._apply_single_nozzle_styling()

    def _apply_single_nozzle_styling(self):
        """Apply custom styling for single nozzle configuration."""
        # Set border radius for top corners of setToolTempButton and extruderButton
        if hasattr(self, 'setToolTempButton') and self.setToolTempButton:
            current_style = self.setToolTempButton.styleSheet()
            # Create proper CSS structure for QPushButton
            border_style = "QPushButton { border-top-right-radius: 15px; }"
            # Combine existing style with new border style
            new_style = current_style + " " + border_style if current_style else border_style
            self.setToolTempButton.setStyleSheet(new_style)
            
        if hasattr(self, 'extruderButton') and self.extruderButton:
            current_style = self.extruderButton.styleSheet()
            # Create proper CSS structure for QPushButton
            border_style = "QPushButton { border-top-left-radius: 15px; border-top-right-radius: 15px; }"
            # Combine existing style with new border style
            new_style = current_style + " " + border_style if current_style else border_style
            self.extruderButton.setStyleSheet(new_style)
            
        # Set border radius for toolTempSpinBox
        if hasattr(self, 'toolTempSpinBox') and self.toolTempSpinBox:
            current_style = self.toolTempSpinBox.styleSheet()
            # Create proper CSS structure for QSpinBox
            border_style = "QSpinBox { border-top-left-radius: 15px; border-bottom-left-radius: 15px; }"
            # Combine existing style with new border style
            new_style = current_style + " " + border_style if current_style else border_style
            self.toolTempSpinBox.setStyleSheet(new_style)

    def coolDownAction(self):
        """'
        Turns all heaters and fans off
        """
        logger.info("ControlScreen.coolDownAction started")
        try:
            self.octoprint_client.gcode(command='M107')
            self.octoprint_client.setToolTemperature({"tool0": 0, "tool1": 0})
            # octopiclient.setToolTemperature({"tool0": 0})
            self.octoprint_client.setBedTemperature(0)
            self.toolTempSpinBox.setProperty("value", 0)
            self.bedTempSpinBox.setProperty("value", 0)
        except Exception as e:
            logger.error("Error in ControlScreen.coolDownAction: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.coolDownAction: {}".format(e), overlay=True)

    def setFeedRate(self):
        """Set the feed rate via OctoPrint and update the printer model."""
        logger.info("ControlScreen.setFeedRate started")
        try:
            feed_rate = self.feedRateSpinBox.value()
            self.octoprint_client.feedrate(feed_rate)
            # Update the printer model to emit signal for home screen
            self.main_window.printer_model.update_feed_rate(feed_rate)
        except Exception as e:
            logger.error("Error in ControlScreen.setFeedRate: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.setFeedRate: {}".format(e), overlay=True)

    def setFlowRate(self):
        """Set the flow rate via OctoPrint and update the printer model."""
        logger.info("ControlScreen.setFlowRate started")
        try:
            flow_rate = self.flowRateSpinBox.value()
            self.octoprint_client.flowrate(flow_rate)
            # Update the printer model to emit signal for home screen
            self.main_window.printer_model.update_flow_rate(flow_rate)
        except Exception as e:
            logger.error("Error in ControlScreen.setFlowRate: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.setFlowRate: {}".format(e), overlay=True)

    def setToolTemp(self):
        """
        Sets the temperature of the tool, depending on the tool selected
        """
        logger.info("ControlScreen.setToolTemp started")
        try:
            if self.toolToggleTemperatureButton.isChecked():
                self.octoprint_client.gcode(command='M104 T1 S' + str(self.toolTempSpinBox.value()))
                # octopiclient.setToolTemperature({"tool1": self.toolTempSpinBox.value()})
            else:
                self.octoprint_client.gcode(command='M104 T0 S' + str(self.toolTempSpinBox.value()))
                # octopiclient.setToolTemperature({"tool0": self.toolTempSpinBox.value()})
        except Exception as e:
            logger.error("Error in ControlScreen.setToolTemp: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.setToolTemp: {}".format(e), overlay=True)

    def preheatBedTemp(self, temp):
        """
        Preheats the bed to the given temperature
        param temp: temperature to preheat to
        """
        logger.info("ControlScreen.preheatBedTemp started")
        try:
            self.octoprint_client.gcode(command='M140 S' + str(temp))
            self.bedTempSpinBox.setProperty("value", temp)
        except Exception as e:
            logger.error("Error in ControlScreen.preheatBedTemp: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.preheatBedTemp: {}".format(e), overlay=True)

    def preheatToolTemp(self, temp):
        """
        Preheats the tool to the given temperature
        param temp: temperature to preheat to
        """
        logger.info("ControlScreen.preheatToolTemp started")
        try:
            if self.toolToggleTemperatureButton.isChecked():
                self.octoprint_client.gcode(command='M104 T1 S' + str(temp))
            else:
                self.octoprint_client.gcode(command='M104 T0 S' + str(temp))
            self.toolTempSpinBox.setProperty("value", temp)
        except Exception as e:
            logger.error("Error in ControlScreen.preheatToolTemp: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.preheatToolTemp: {}".format(e), overlay=True)

    def selectToolTemperature(self):
        """
        Selects the tool whose temperature needs to be changed.
        It accordingly changes the button text.it also updates the status of the other toggle buttons.
        """
        logger.info("ControlScreen.selectToolTemperature started")
        try:
            # Update the spinbox with the target temperature of the newly selected tool
            self._update_tool_temperature_spinbox()
        except Exception as e:
            logger.error("Error in ControlScreen.selectToolTemperature: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.selectToolTemperature: {}".format(e), overlay=True)

    def selectToolMotion(self):
        """
        Selects the tool whose temperature needs to be changed. It accordingly changes the button text. it also updates the status of the other toggle buttons
        """
        logger.info("ControlScreen.selectToolMotion started")
        try:
            if self.toolToggleMotionButton.isChecked():
                self.octoprint_client.selectTool(1)
                self.setActiveExtruder(1)

            else:
                self.octoprint_client.selectTool(0)
                self.setActiveExtruder(0)
        except Exception as e:
            logger.error("Error in ControlScreen.selectToolMotion: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.selectToolMotion: {}".format(e), overlay=True)

    def setStep(self, stepRate):
        """
        Sets the class variable "Step" which would be needed for movement and joging
        :param stepRate: step multiplier for movement in the move
        :return: nothing
        """
        logger.info("ControlScreen.setStep started")
        try:
            if stepRate == 100:
                self.step100mmButton.setFlat(True)
                self.step1mmButton.setFlat(False)
                self.step10mmButton.setFlat(False)
                self.step = 100
            if stepRate == 1:
                self.step100mmButton.setFlat(False)
                self.step1mmButton.setFlat(True)
                self.step10mmButton.setFlat(False)
                self.step = 1
            if stepRate == 10:
                self.step100mmButton.setFlat(False)
                self.step1mmButton.setFlat(False)
                self.step10mmButton.setFlat(True)
                self.step = 10
        except Exception as e:
            logger.error("Error in ControlScreen.setStep: {}".format(e))
            dialog.WarningOk(self, "Error in ControlScreen.setStep: {}".format(e), overlay=True)

    def setActiveExtruder(self, activeNozzle):
        """
        Sets the active extruder, and changes the UI accordingly
        """
        logger.info("control_screen.setActiveExtruder started")
        try:
            if activeNozzle == 0:
                self.toolToggleMotionButton.setChecked(False)
                self.toolToggleMotionButton.setText("0")
                self.activeExtruder = 0
                # For dual nozzle, also update temperature toggle
                if is_dual_nozzle_printer() and hasattr(self, 'toolToggleTemperatureButton'):
                    self.toolToggleTemperatureButton.setChecked(False)
            elif activeNozzle == 1:
                self.toolToggleMotionButton.setChecked(True)
                self.toolToggleMotionButton.setText("1")
                self.activeExtruder = 1
                # For dual nozzle, also update temperature toggle
                if is_dual_nozzle_printer() and hasattr(self, 'toolToggleTemperatureButton'):
                    self.toolToggleTemperatureButton.setChecked(True)
            
            # Update temperature spinbox to show the correct tool's target temperature
            self._update_tool_temperature_spinbox()
            
        except Exception as e:
            logger.error("Error in control_screen.setActiveExtruder: {}".format(e))
            dialog.WarningOk(self, "Error in control_screen.setActiveExtruder: {}".format(e), overlay=True)

    def _update_tool_temperature_spinbox(self):
        """Helper method to update tool temperature spinbox based on current tool selection."""
        try:
            if is_dual_nozzle_printer() and hasattr(self, 'toolToggleTemperatureButton'):
                if self.toolToggleTemperatureButton.isChecked():
                    # Tool 1 is selected
                    tool_target = self.main_window.printer_model.temperatures.get('tool1Target', 0)
                else:
                    # Tool 0 is selected
                    tool_target = self.main_window.printer_model.temperatures.get('tool0Target', 0)
            else:
                # Single nozzle, always use tool0
                tool_target = self.main_window.printer_model.temperatures.get('tool0Target', 0)
            
            self.toolTempSpinBox.setValue(tool_target)
        except Exception as e:
            self.logger.error(f"Error updating tool temperature spinbox: {e}")

    def buttonStatusUpdate(self, status):
        """Update ControlScreen UI elements based on printer status"""
        try:
            # Disable motion controls during printing
            if status == "Printing":
                self.motionTab.setDisabled(True)
            else:  # Paused, Offline, Operational, etc.
                self.motionTab.setDisabled(False)
                    
            # TODO: Add other control-specific UI updates based on status
            # For example: disable certain temperature controls, etc.
        except Exception as e:
            logger.error(f"Error updating ControlScreen UI for status {status}: {e}")
            dialog.WarningOk(self, f"Error updating ControlScreen UI for status {status}: {e}", overlay=True)

    def on_klipper_state_changed(self, state):
        """Disable all buttons except back button when Klipper is not ready"""
        try:
            state_lower = str(state).strip().lower()
            # Accept multiple states as "ready": ready, operational, idle
            # Also allow unknown state to keep buttons enabled (temporary for debugging)
            is_ready = state_lower in ['ready', 'operational', 'idle', 'unknown']
            self.logger.info(f"ControlScreen: Klipper state changed to: '{state}' (normalized: '{state_lower}'), is_ready: {is_ready}")
            
            # List all buttons and controls that should be disabled when Klipper is not ready
            # Keep the back button always enabled
            controls_to_disable = [
                # Feed Rate controls
                self.setFeedRateButton, self.moveZPBabyStep, self.moveZMBabyStep,
                
                # Flow rate controls
                self.setFlowRateButton,
                
                # Temperature controls
                self.fanOnButton, self.fanOffButton, self.cooldownButton,
                self.setToolTempButton, self.setBedTempButton, self.toolToggleTemperatureButton,
                self.tool180PreheatButton, self.tool250PreheatButton,
                self.bed60PreheatButton, self.bed100PreheatButton,
                
                # Motion controls
                self.step1mmButton, self.step10mmButton, self.step100mmButton,
                self.moveXPButton, self.moveXMButton, self.moveYPButton, self.moveYMButton,
                self.motorOffButton, self.homeXYButton, self.moveZMButton, self.moveZPButton,
                self.homeZButton, self.toolToggleMotionButton, self.extruderButton, self.retractButton,
                
                # Preference controls
                self.toggleFilamentRunoutButton, self.toggleFilamentJamButton,
                self.toggleAutoResumeButton, self.toggleCheckPrintCompatibilityButton,
                self.togglePrintRestoreButton, self.toggleFirmwareUpdateButton,
                
                # Spinboxes
                self.feedRateSpinBox, self.flowRateSpinBox, self.toolTempSpinBox, self.bedTempSpinBox
            ]
            
            # Enable/disable controls based on Klipper state
            for control in controls_to_disable:
                if control:  # Check if control exists (some may be None)
                    control.setEnabled(is_ready)
            
            # Also disable entire tabs when not ready for better visual feedback
            if hasattr(self, 'tuneTab') and self.tuneTab:
                self.tuneTab.setEnabled(is_ready)
            if hasattr(self, 'temperatureTab') and self.temperatureTab:
                self.temperatureTab.setEnabled(is_ready)
            if hasattr(self, 'motionTab') and self.motionTab:
                # Motion tab has additional logic in buttonStatusUpdate, so only apply if not printing
                if hasattr(self.main_window.printer_model, 'printer_status'):
                    status = getattr(self.main_window.printer_model, 'printer_status', '')
                    if status != "Printing":  # Don't override printing restriction
                        self.motionTab.setEnabled(is_ready)
            if hasattr(self, 'preferencesTab') and self.preferencesTab:
                self.preferencesTab.setEnabled(is_ready)
                
        except Exception as e:
            self.logger.error(f"Error updating ControlScreen UI for Klipper state {state}: {e}")

    def toggleFilamentRunout(self):
        """Toggle filament runout sensor persistent preference and apply live state."""
        logger.info("ControlScreen.toggleFilamentRunout started")
        try:
            enabled = self.toggleFilamentRunoutButton.isChecked()
            # Update model preference (persists)
            self.main_window.printer_model.set_filament_runout_pref(enabled, persist=True)
            # Apply immediate state depending on current print status
            if self.main_window.printer_model.printer_status in ["Printing", "Paused"]:
                self.main_window.controller.apply_filament_sensor_state()
        except Exception as e:
            logger.error(f"Error in ControlScreen.toggleFilamentRunout: {e}")
            dialog.WarningOk(self, f"Error in ControlScreen.toggleFilamentRunout: {e}", overlay=True)

    def toggleFilamentJam(self):
        """Toggle filament jam sensor persistent preference and apply live state."""
        logger.info("ControlScreen.toggleFilamentJam started")
        try:
            enabled = self.toggleFilamentJamButton.isChecked()
            self.main_window.printer_model.set_filament_jam_pref(enabled, persist=True)
            if self.main_window.printer_model.printer_status in ["Printing", "Paused"]:
                self.main_window.controller.apply_filament_sensor_state()
        except Exception as e:
            logger.error(f"Error in ControlScreen.toggleFilamentJam: {e}")
            dialog.WarningOk(self, f"Error in ControlScreen.toggleFilamentJam: {e}", overlay=True)

    def toggleAutoResume(self):
        """Toggle auto-resume on power outage"""
        logger.info("ControlScreen.toggleAutoResume started")
        try:
            enabled = self.toggleAutoResumeButton.isChecked()
            # Update model preference (persists)
            self.main_window.printer_model.set_auto_resume_pref(enabled, persist=True)
            # Apply the setting to OctoPrint via the TwinDragonPrintRestore plugin
            self.main_window.octoprint_client.savePrintRestoreSettings(
                restore=enabled,
                enabled=self.main_window.printer_model.print_restore_enabled,
                interval=1  # Default interval of 1 second
            )
            self.logger.info(f"Auto-resume {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logger.error(f"Error in ControlScreen.toggleAutoResume: {e}")
            dialog.WarningOk(self, f"Error in ControlScreen.toggleAutoResume: {e}", overlay=True)

    def togglePrintRestore(self):
        """Toggle print restore functionality"""
        logger.info("ControlScreen.togglePrintRestore started")
        try:
            enabled = self.togglePrintRestoreButton.isChecked()
            # Update model preference (persists)
            self.main_window.printer_model.set_print_restore_pref(enabled, persist=True)
            # Enable/disable the auto-resume button based on print restore state
            self.toggleAutoResumeButton.setEnabled(enabled)
            # If print restore is disabled, also disable auto-resume
            if not enabled:
                self.toggleAutoResumeButton.setChecked(False)
                self.main_window.printer_model.set_auto_resume_pref(False, persist=True)
            # Apply the setting to OctoPrint via the TwinDragonPrintRestore plugin
            self.main_window.octoprint_client.savePrintRestoreSettings(
                restore=self.main_window.printer_model.auto_resume_enabled,
                enabled=enabled,
                interval=1  # Default interval of 1 second
            )
            self.logger.info(f"Print restore {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logger.error(f"Error in ControlScreen.togglePrintRestore: {e}")
            dialog.WarningOk(self, f"Error in ControlScreen.togglePrintRestore: {e}", overlay=True)

    def toggleCheckPrintCompatibility(self):
        """Toggle check print compatibility preference and persist the setting."""
        logger.info("ControlScreen.toggleCheckPrintCompatibility started")
        try:
            enabled = self.toggleCheckPrintCompatibilityButton.isChecked()
            # Update model preference (persists)
            self.main_window.printer_model.set_print_compatibility_check_pref(enabled, persist=True)
            self.logger.info(f"Print compatibility check {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logger.error(f"Error in ControlScreen.toggleCheckPrintCompatibility: {e}")
            dialog.WarningOk(self, f"Error in ControlScreen.toggleCheckPrintCompatibility: {e}", overlay=True)

    def toggleFirmwareUpdate(self):
        """Toggle firmware update check preference and persist the setting."""
        logger.info("ControlScreen.toggleFirmwareUpdate started")
        try:
            enabled = self.toggleFirmwareUpdateButton.isChecked()
            # Update model preference (persists)
            self.main_window.printer_model.set_firmware_update_check_pref(enabled, persist=True)
            self.logger.info(f"Firmware update check {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logger.error(f"Error in ControlScreen.toggleFirmwareUpdate: {e}")
            dialog.WarningOk(self, f"Error in ControlScreen.toggleFirmwareUpdate: {e}", overlay=True)

    def toggleAdvancedDebugging(self):
        """Toggle advanced debugging mode preference and persist the setting."""
        logger.info("ControlScreen.toggleAdvancedDebugging started")
        try:
            enabled = self.advaceDebuggingModeButton.isChecked()
            # Update model preference (persists and applies logging changes immediately)
            self.main_window.printer_model.set_advanced_debugging_pref(enabled, persist=True)
            self.logger.info(f"Advanced debugging mode {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            logger.error(f"Error in ControlScreen.toggleAdvancedDebugging: {e}")
            dialog.WarningOk(self, f"Error in ControlScreen.toggleAdvancedDebugging: {e}", overlay=True)

    def apply_scrollbar_styling(self):
        """Apply custom scrollbar styling to all scroll areas in the control screen."""
        try:
            # Import QScrollArea and QScrollBar here to avoid import issues
            from PyQt5.QtWidgets import QScrollArea, QScrollBar
            from PyQt5.QtCore import QTimer
            
            # Find all scroll areas in the widget
            scroll_areas = self.findChildren(QScrollArea)
            
            # More aggressive scrollbar style with higher specificity
            scrollbar_style = """
            QScrollArea {
                background-color: transparent !important;
                border: none !important;
            }
            
            QScrollArea > QWidget {
                background-color: transparent !important;
            }
            
            QScrollArea > QWidget > QWidget {
                background-color: transparent !important;
            }
            
            QScrollBar:vertical {
                border: 1px solid black !important;
                border-radius: 5px !important;
                background-color: rgb(40,40,40) !important;
                width: 80px !important;
                margin: 70px 0 70px 0 !important;
            }
            
            QScrollBar::handle:vertical {
                border-radius: 5px !important;
                background: qlineargradient(spread:pad, x1:0, y1:1, x2:0, y2:0.188, stop:0 rgba(180, 180, 180, 255), stop:1 rgba(255, 255, 255, 255)) !important;
                min-height: 20px !important;
            }
            
            QScrollBar::add-line:vertical {
                border: 1px solid black !important;
                background: qlineargradient(spread:pad, x1:0, y1:1, x2:0, y2:0.188, stop:0 rgba(180, 180, 180, 255), stop:1 rgba(255, 255, 255, 255)) !important;
                height: 65px !important;
                border-radius: 5px !important;
                subcontrol-position: bottom !important;
                subcontrol-origin: margin !important;
            }
            
            QScrollBar::sub-line:vertical {
                border: 1px solid black !important;
                background: qlineargradient(spread:pad, x1:0, y1:1, x2:0, y2:0.188, stop:0 rgba(180, 180, 180, 255), stop:1 rgba(255, 255, 255, 255)) !important;
                height: 65px !important;
                border-radius: 5px !important;
                subcontrol-position: top !important;
                subcontrol-origin: margin !important;
            }
            
            QScrollBar::up-arrow:vertical {
                image: url(:/Navigation/img/Navigation/arrows.png) !important;
                width: 40px !important;
                height: 40px !important;
                padding: 5px !important;
            }
            
            QScrollBar::down-arrow:vertical {
                image: url(:/Navigation/img/Navigation/arrows-5.png) !important;
                width: 40px !important;
                height: 40px !important;
                padding: 5px !important;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none !important;
            }
            """
            
            # Apply the style to each scroll area
            for scroll_area in scroll_areas:
                scroll_area.setStyleSheet(scrollbar_style)
                
                # Also try to find and style scrollbars directly
                scrollbars = scroll_area.findChildren(QScrollBar)
                for scrollbar in scrollbars:
                    scrollbar.setStyleSheet(scrollbar_style)
                    
                self.logger.info(f"Applied scrollbar styling to scroll area: {scroll_area.objectName()}")
            
            # Schedule a delayed re-application to catch scrollbars that appear later
            def reapply_scrollbar_styling():
                try:
                    current_scroll_areas = self.findChildren(QScrollArea)
                    for scroll_area in current_scroll_areas:
                        scroll_area.setStyleSheet(scrollbar_style)
                        scrollbars = scroll_area.findChildren(QScrollBar)
                        for scrollbar in scrollbars:
                            scrollbar.setStyleSheet(scrollbar_style)
                except Exception as e:
                    self.logger.error(f"Error in delayed scrollbar styling: {e}")
            
            # Apply after a short delay to catch dynamically created scrollbars
            QTimer.singleShot(1000, reapply_scrollbar_styling)
                
            if scroll_areas:
                self.logger.info(f"Applied scrollbar styling to {len(scroll_areas)} scroll areas with tab widget context")
                
        except Exception as e:
            self.logger.error(f"Error applying scrollbar styling: {e}", exc_info=True)

    def homeXYAndSync(self):
        """Home XY and sync tool state - assumes homing switches to T0"""
        try:
            self.logger.info("Homing XY and syncing tool state...")
            
            # Do the homing
            self.octoprint_client.home(['x', 'y'])
            
            # For dual nozzle printers, homing typically switches to T0
            # So we force sync to T0 after a short delay
            if is_dual_nozzle_printer():
                QtCore.QTimer.singleShot(2000, lambda: self.syncToT0AfterHoming())
                
        except Exception as e:
            self.logger.error(f"Error in homeXYAndSync: {e}")

    def homeZAndSync(self):
        """Home Z and sync tool state - assumes homing switches to T0"""
        try:
            self.logger.info("Homing Z and syncing tool state...")
            
            # Do the homing
            self.octoprint_client.home(['z'])
            
            # For dual nozzle printers, homing typically switches to T0
            # So we force sync to T0 after a short delay
            if is_dual_nozzle_printer():
                QtCore.QTimer.singleShot(1500, lambda: self.syncToT0AfterHoming())
                
        except Exception as e:
            self.logger.error(f"Error in homeZAndSync: {e}")

    def syncToT0AfterHoming(self):
        """Force sync UI to T0 after homing (since homing typically switches to T0)"""
        try:
            self.logger.info("Syncing UI to T0 after homing operation")
            # Directly update the UI to reflect T0 as active
            self.setActiveExtruder(0)
        except Exception as e:
            self.logger.error(f"Error syncing to T0 after homing: {e}")
