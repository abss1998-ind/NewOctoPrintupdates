import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QToolButton, QPushButton, QLabel, QProgressBar
from PyQt5 import QtGui, QtCore
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils.printer_ui_config import apply_nozzle_config_to_screen
from utils.styles import printer_status_green, printer_status_red, printer_status_amber
from utils import dialog
from utils import styles
from utils.network_utils import getIP
from utils.helpers import run_async
import time
import ui.resources.resource_rc  # Import resources for Qt resource system


class HomeScreen(QWidget):
    def __init__(self, main_window, minimalUI=False):
        super(HomeScreen, self).__init__()
        self.logger = get_logger(self.__class__.__name__)
        self.main_window = main_window
        self.minimalUI = minimalUI
        self.octoprint_client = main_window.octoprint_client
        self.printer_connected = False
        self.is_printing = False
        self.temperature_data = {"tool0": {"actual": 0, "target": 0},
                                 "tool1": {"actual": 0, "target": 0},
                                 "bed": {"actual": 0, "target": 0}}

        # Job info
        self.current_file = "No file selected"
        self.current_image = None
        self.print_progress = 0
        self.print_time = "-"
        self.time_left = "-"
        self.printerStatusText = ""
        self._last_status = ""


        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "home_screen.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("HomeScreen UI loaded successfully")
        except Exception as e:
            self.logger.exception(f"Failed to load HomeScreen UI file: {e}")

        """ ---------- Initialize UI components by group ---------- """

        # Control buttons
        self.doorLockButton = self.findChild(QToolButton, "doorLockButton")  # Done
        self.menuButton = self.findChild(QPushButton, "menuButton")  # Done
        self.stopButton = self.findChild(QPushButton, "stopButton")  # Done
        self.playPauseButton = self.findChild(QPushButton, "playPauseButton")
        self.controlButton = self.findChild(QPushButton, "controlButton")

        # Temperature displays - Tool 0
        self.tool0TargetTemperature = self.findChild(QLabel, "tool0TargetTemperature")
        self.tool0ActualTemperature = self.findChild(QLabel, "tool0ActualTemperature")
        self.tool0TempBar = self.findChild(QProgressBar, "tool0TempBar")
        self.tool0Label = self.findChild(QLabel, "tool0Label")

        # Temperature displays - Tool 1
        self.tool1TargetTemperature = self.findChild(QLabel, "tool1TargetTemperature")
        self.tool1ActualTemperature = self.findChild(QLabel, "tool1ActualTemperature")
        self.tool1TempBar = self.findChild(QProgressBar, "tool1TempBar")
        self.tool1Label = self.findChild(QLabel, "tool1Label")

        # Temperature displays - Bed
        self.bedTargetTemperature = self.findChild(QLabel, "bedTargetTemperature")
        self.bedActualTemperature = self.findChild(QLabel, "bedActualTemperature")
        self.bedTempBar = self.findChild(QProgressBar, "bedTempBar")

        # Status components
        self.printerStatus = self.findChild(QLabel, "printerStatus")
        self.printerStatusColour = self.findChild(QLabel, "printerStatusColour")
        self.ipStatus = self.findChild(QLabel, "ipStatus")

        # Print information
        self.fileName = self.findChild(QLabel, "fileName")
        self.printTime = self.findChild(QLabel, "printTime")
        self.timeLeft = self.findChild(QLabel, "timeLeft")
        self.printProgressBar = self.findChild(QProgressBar, "printProgressBar")
        self.printPreviewMain = self.findChild(QLabel, "printPreviewMain")

        # Feed rate and flow rate labels
        self.feedRateLabel = self.findChild(QLabel, "feedRateLabel")
        self.flowRateLabel = self.findChild(QLabel, "flowRateLabel")

        # Validate UI components
        all_components = [
            self.doorLockButton, self.menuButton, self.stopButton, self.playPauseButton, self.controlButton,
            self.tool0TargetTemperature, self.tool0ActualTemperature, self.tool0TempBar, self.tool0Label,
            self.tool1TargetTemperature, self.tool1ActualTemperature, self.tool1TempBar, self.tool1Label,
            self.bedTargetTemperature, self.bedActualTemperature, self.bedTempBar,
            self.printerStatus, self.printerStatusColour, self.ipStatus,
            self.fileName, self.printTime, self.timeLeft, self.printProgressBar, self.printPreviewMain,
            self.feedRateLabel, self.flowRateLabel
        ]
        check_ui_elements(self, all_components, "HomeScreen")

        # ! Local Signal-Slot Connections
        # Connect signals from model to slots from home_screen
        self.main_window.printer_model.status_updated.connect(self.updatePrinterStatus)
        self.main_window.printer_model.print_status_updated.connect(self.updatePrintStatus)
        self.main_window.printer_model.temperatures_updated.connect(self.updateTemperature)
        self.main_window.printer_model.active_extruder_changed.connect(self.setActiveExtruder)
        # Connect feed rate and flow rate signals
        self.main_window.printer_model.feed_rate_updated.connect(self.updateFeedRate)
        self.main_window.printer_model.flow_rate_updated.connect(self.updateFlowRate)
        # New: reflect loaded filament/nozzle
        try:
            self.main_window.printer_model.tool_bay_states_loaded.connect(self.on_tool_states_loaded)
            self.main_window.printer_model.tool_bay_state_changed.connect(self.on_tool_state_changed)
        except Exception as e:
            self.logger.warning(f"Tool state signals not available: {e}")

        # Connect button signals to their handlers
        self.doorLockButton.clicked.connect(self.toggle_door_lock)
        self.menuButton.clicked.connect(self.open_menu)
        self.stopButton.clicked.connect(self.stop_print)
        self.playPauseButton.clicked.connect(self.play_pause_print)
        self.controlButton.clicked.connect(self.open_control_panel)

        # Initialize UI state
        # Update temperature displays
        self.tool0ActualTemperature.setText("0°C")
        self.tool0TargetTemperature.setText("0°C")
        self.tool0TempBar.setValue(0)

        self.tool1ActualTemperature.setText("0°C")
        self.tool1TargetTemperature.setText("0°C")
        self.tool1TempBar.setValue(0)

        self.bedActualTemperature.setText("0°C")
        self.bedTargetTemperature.setText("0°C")
        self.bedTempBar.setValue(0)

        # Update print info
        self.fileName.setText(self.current_file)
        self.printTime.setText(self.print_time)
        self.timeLeft.setText(self.time_left)
        self.printProgressBar.setValue(self.print_progress)

        # Initialize feed rate and flow rate labels
        self.feedRateLabel.setText("100%")
        self.flowRateLabel.setText("100%")
        
        # Set initial values from printer model if available
        try:
            if hasattr(self.main_window.printer_model, 'current_feed_rate'):
                self.feedRateLabel.setText(f"{self.main_window.printer_model.current_feed_rate}%")
            if hasattr(self.main_window.printer_model, 'current_flow_rate'):
                self.flowRateLabel.setText(f"{self.main_window.printer_model.current_flow_rate}%")
        except Exception as e:
            self.logger.debug(f"Could not initialize rate labels from model: {e}")

        # Update printer status
        self.printerStatus.setText("Disconnected")
        self.printerStatusColour.setStyleSheet(printer_status_red)
        self.ipStatus.setText("Not Connected")

        self.setActiveExtruder(0)  # Default to extruder 0

        if self.minimalUI:
            # Disable buttons in Home Screen
            self.stopButton.setEnabled(False)
            self.controlButton.setEnabled(False)
            self.playPauseButton.setEnabled(False)
            self.doorLockButton.setEnabled(False)
            # Show a visual indicator on the home screen that we're in limited mode
            self.printerStatus.setText("Disconnected - Limited Mode")
            self.printerStatusColour.setStyleSheet(printer_status_red)
            self.setIPStatus()
        else:
            # Enable buttons in Home Screen
            self.stopButton.setEnabled(True)
            self.controlButton.setEnabled(True)
            self.playPauseButton.setEnabled(True)
            self.doorLockButton.setEnabled(False)
            # Update home screen connection status
            self.printerStatus.setText("Connected")
            self.printerStatusColour.setStyleSheet(printer_status_green)
            self.setIPStatus()

        # Initialize tool labels from model if available
        try:
            m = self.main_window.printer_model
            if hasattr(m, 'tools'):
                self.on_tool_states_loaded(m.tools)
        except Exception as e:
            self.logger.debug(f"Unable to init tool labels: {e}")

        # Apply nozzle configuration
        self.apply_nozzle_configuration()

    def apply_nozzle_configuration(self):
        """Hide dual nozzle elements for single nozzle configuration."""
        apply_nozzle_config_to_screen(self, 'home_screen')

    def updatePrinterStatus(self, status):
        """Update the status bar and enable/disable relevant buttons.
        
        This is a slot for the signal emitted from the thread that constantly polls 
        for printer status. Updates only local HomeScreen UI elements.
        
        Args:
            status: String of the status text
        """
        if getattr(self, "_last_status", None) != status:
            self.logger.info("HomeScreen.updatePrinterStatus called with status: {}".format(status))
            self._last_status = status
        try:
            self.printerStatusText = status
            self.printerStatus.setText(status)

            # Update status color indicator
            if status == "Printing":  # Green
                self.printerStatusColour.setStyleSheet(styles.printer_status_green)
            elif status == "Offline":  # Red
                self.printerStatusColour.setStyleSheet(styles.printer_status_red)
            elif status == "Paused":  # Amber
                self.printerStatusColour.setStyleSheet(styles.printer_status_amber)
            elif status == "Operational":  # Blue
                self.printerStatusColour.setStyleSheet(styles.printer_status_blue)

            # Update HomeScreen buttons based on status
            if status == "Printing":
                self.playPauseButton.setChecked(True)
                self.stopButton.setDisabled(False)
                self.doorLockButton.setDisabled(False)
            elif status == "Paused":
                self.playPauseButton.setChecked(False)
                self.stopButton.setDisabled(False)
                self.doorLockButton.setDisabled(False)
            else:  # Offline, Operational, etc.
                self.stopButton.setDisabled(True)
                self.playPauseButton.setChecked(False)
                self.doorLockButton.setDisabled(True)

        except Exception as e:
            self.logger.error("Error in HomeScreen.updatePrinterStatus: {}".format(e))
            dialog.WarningOk(self, "Error in HomeScreen.updatePrinterStatus: {}".format(e), overlay=True)

    def updatePrintStatus(self, file):
        """Display information about a particular file on the home page.
        
        This is a slot for the signal emitted from the thread that keeps polling 
        for printer status. Updates at 1Hz for frequently changing data.
        
        Args:
            file: dict of all the attributes of a particular file
        """
        try:
            if file["job"] is None:
                self.current_image = None
                self.timeLeft.setText("-")
                self.fileName.setText("-")
                self.printProgressBar.setValue(0)
                self.printTime.setText("-")
                self.playPauseButton.setDisabled(True)  # if file is not available, disable playPauseButton
                # Reset preview image to default thumbnail when no file is loaded
                self.printPreviewMain.setPixmap(QtGui.QPixmap(":/Logos & Branding/img/Logos/thumbnail.png"))

            else:
                self.playPauseButton.setDisabled(False)  # if file available, make play button visible
                self.fileName.setText(file['job']['file']['name'])
                self.current_file = file['job']['file']['name']
                if file['progress']['printTime'] is None:
                    self.printTime.setText("-")
                else:
                    m, s = divmod(file['progress']['printTime'], 60)
                    h, m = divmod(m, 60)
                    d, h = divmod(h, 24)
                    self.printTime.setText("%d:%d:%02d:%02d" % (d, h, m, s))

                if file['progress']['printTimeLeft'] is None:
                    self.timeLeft.setText("-")
                else:
                    m, s = divmod(file['progress']['printTimeLeft'], 60)
                    h, m = divmod(m, 60)
                    d, h = divmod(h, 24)
                    self.timeLeft.setText("%d:%d:%02d:%02d" % (d, h, m, s))

                if file['progress']['completion'] is None:
                    self.printProgressBar.setValue(0)
                else:
                    self.printProgressBar.setValue(file['progress']['completion'])

                """
                If image is available from server, set it, otherwise display default image.
                If the image was already loaded, don't load it again.
                """
                if self.current_image != self.current_file:
                    self.current_image = self.current_file
                    img = self.octoprint_client.getImage(self.current_file)
                    if img:
                        pixmap = QtGui.QPixmap()
                        pixmap.loadFromData(img)
                        # Scale image to fit the label size while maintaining square aspect ratio
                        label_size = self.printPreviewMain.size()
                        square_size = min(label_size.width(), label_size.height())
                        scaled_pixmap = pixmap.scaled(square_size, square_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                        self.printPreviewMain.setPixmap(scaled_pixmap)
                    else:
                        # Use resource path for thumbnail image
                        self.printPreviewMain.setPixmap(QtGui.QPixmap(":/Logos & Branding/img/Logos/thumbnail.png"))
        except Exception as e:
            self.logger.error("Error in HomeScreen.updatePrintStatus: {}".format(e))
            dialog.WarningOk(self, "Error in HomeScreen.updatePrintStatus: {}".format(e), overlay=True)

    def updateTemperature(self, temperature):
        """
        Slot that gets a signal originating from the thread that keeps polling for printer status
        runs at 1HZ, so do things that need to be constantly updated only. This also controls the cooling fan depending on the temperatures
        :param temperature: dict containing key:value pairs with keys being the tools, bed and their values being their corresponding temperratures
        """
        try:
            # ideally the none to 0 conversion should happen here
            if temperature['tool0Actual'] is None:
                temperature['tool0Actual'] = 0
            if temperature['tool0Target'] is None:
                temperature['tool0Target'] = 0
            if temperature['tool1Actual'] is None:
                temperature['tool1Actual'] = 0
            if temperature['tool1Target'] is None:
                temperature['tool1Target'] = 0
            if temperature['bedActual'] is None:
                temperature['bedActual'] = 0
            if temperature['bedTarget'] is None:
                temperature['bedTarget'] = 0

            # Update extruder 0 temperature
            if temperature['tool0Target'] == 0:
                self.tool0TempBar.setMaximum(300)
                self.tool0TempBar.setStyleSheet(styles.bar_heater_cold)
            elif temperature['tool0Actual'] <= temperature['tool0Target']:
                self.tool0TempBar.setMaximum(temperature['tool0Target'])
                self.tool0TempBar.setStyleSheet(styles.bar_heater_heating)
            else:
                self.tool0TempBar.setMaximum(temperature['tool0Actual'])
            self.tool0TempBar.setValue(temperature['tool0Actual'])
            self.tool0ActualTemperature.setText(str(int(temperature['tool0Actual'])) + "°C")
            self.tool0TargetTemperature.setText(str(int(temperature['tool0Target'])) + "°C")

            # Update extruder 1 temperature
            if temperature['tool1Target'] == 0:
                self.tool1TempBar.setMaximum(300)
                self.tool1TempBar.setStyleSheet(styles.bar_heater_cold)
            elif temperature['tool1Actual'] <= temperature['tool1Target']:
                self.tool1TempBar.setMaximum(temperature['tool1Target'])
                self.tool1TempBar.setStyleSheet(styles.bar_heater_heating)
            else:
                self.tool1TempBar.setMaximum(temperature['tool1Actual'])
            self.tool1TempBar.setValue(temperature['tool1Actual'])
            self.tool1ActualTemperature.setText(str(int(temperature['tool1Actual'])) + "°C")
            self.tool1TargetTemperature.setText(str(int(temperature['tool1Target'])) + "°C")

            # Update bed temperature
            if temperature['bedTarget'] == 0:
                self.bedTempBar.setMaximum(150)
                self.bedTempBar.setStyleSheet(styles.bar_heater_cold)
            elif temperature['bedActual'] <= temperature['bedTarget']:
                self.bedTempBar.setMaximum(temperature['bedTarget'])
                self.bedTempBar.setStyleSheet(styles.bar_heater_heating)
            else:
                self.bedTempBar.setMaximum(temperature['bedActual'])
            self.bedTempBar.setValue(temperature['bedActual'])
            self.bedActualTemperature.setText(str(int(temperature['bedActual'])) + "°C")
            self.bedTargetTemperature.setText(str(int(temperature['bedTarget'])) + "°C")

        except (KeyError, TypeError, ValueError) as e:
            self.logger.warning(f"Error updating temperature display: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error in updateTemperature: {e}")

    @run_async
    def setIPStatus(self):
        """
        Function to update IP address of printer on the status bar. Refreshes at a particular interval.
        """
        try:
            while True:
                try:
                    if getIP("eth0"):
                        self.ipStatus.setText(getIP("eth0"))
                    elif getIP("wlan0"):
                        self.ipStatus.setText(getIP("wlan0"))
                    else:
                        self.ipStatus.setText("Not connected")

                except (OSError, AttributeError) as e:
                    self.logger.warning(f"Error getting IP address: {e}")
                    self.ipStatus.setText("Not connected")
                time.sleep(120)
        except Exception as e:
            self.logger.error("Error in HomeScreen.setIPStatus: {}".format(e))

    # ! Below are the boilerplate functions

    def toggle_door_lock(self):
        """
        function that toggles locking and unlocking the front door
        :return:
        """
        self.logger.info("HomeScreen.doorLock started")
        try:
            self.octoprint_client.gcode(command='DoorToggle')
            self.octoprint_client.overrideDoorLock()
        except Exception as e:
            self.logger.error("Error in HomeScreen.doorLock: {}".format(e))
            dialog.WarningOk(self, "Error in HomeScreen.doorLock: {}".format(e), overlay=True)

    def open_menu(self):
        """Navigate to menu screen"""
        self.main_window.switch_to_menu_screen()
        self.logger.debug("Menu button clicked")

    def stop_print(self):
        """Stop current print job"""
        # if not self.printer_connected:
        #     return

        self.logger.info("HomeScreen.stopActionMessageBox started")
        self.logger.debug("Stop Print button clicked")

        # Send command to OctoPrint if connected
        if self.octoprint_client:
            try:
                if dialog.WarningYesNo(self, "Are you sure you want to stop the print?"):
                    self.octoprint_client.cancelPrint()
            except Exception as e:
                self.logger.error("Error in HomeScreen.stopActionMessageBox: {}".format(e))
                dialog.WarningOk(self, "Error in HomeScreen.stopActionMessageBox: {}".format(e), overlay=True)

    def play_pause_print(self):
        """Play or pause print job based on current state"""
        # if not self.printer_connected:
        #     return

        is_paused = self.playPauseButton.isChecked()
        self.logger.debug(f"Play/Pause button clicked: {'Pausing' if not is_paused else 'Resuming'}")

        if self.octoprint_client:
            try:
                if self.printerStatusText == "Operational":
                    if self.playPauseButton.isChecked():
                        self.main_window.controller.checkKlipperPrinterCFG()
                        self.octoprint_client.startPrint()
                elif self.printerStatusText == "Printing":
                    self.octoprint_client.pausePrint()
                elif self.printerStatusText == "Paused":
                    self.octoprint_client.pausePrint()
            except Exception as e:
                self.logger.error("Error in home_screen.playPauseAction: {}".format(e))
                dialog.WarningOk(self, "Error in home_screen.playPauseAction: {}".format(e), overlay=True)

    def open_control_panel(self):
        """Navigate to control panel screen"""
        self.main_window.switch_to_control_screen()
        self.logger.debug("Control Panel button clicked")

    def setActiveExtruder(self, activeNozzle):
        """
        Sets the active extruder, and changes the UI accordingly
        """
        self.logger.info("home_screen.setActiveExtruder started with activeNozzle: {}".format(activeNozzle))
        try:
            # Debug: Check if labels exist
            self.logger.debug("tool0Label found: {}".format(self.tool0Label is not None))
            self.logger.debug("tool1Label found: {}".format(self.tool1Label is not None))

            if activeNozzle == 0:
                pixmap = QtGui.QPixmap(":/Icons/img/icons/activeNozzle.png")
                if not pixmap.isNull():
                    self.tool0Label.setPixmap(pixmap)
                    self.logger.debug("Set tool0Label to activeNozzle.png")
                else:
                    self.logger.error("Failed to load activeNozzle.png pixmap")
                pixmap = QtGui.QPixmap(":/Icons/img/icons/Nozzle.png")
                if not pixmap.isNull():
                    self.tool1Label.setPixmap(pixmap)
                    self.logger.debug("Set tool1Label to Nozzle.png")
                else:
                    self.logger.error("Failed to load Nozzle.png pixmap")
            elif activeNozzle == 1:
                pixmap = QtGui.QPixmap(":/Icons/img/icons/Nozzle.png")
                if not pixmap.isNull():
                    self.tool0Label.setPixmap(pixmap)
                    self.logger.debug("Set tool0Label to Nozzle.png")
                else:
                    self.logger.error("Failed to load Nozzle.png pixmap")
                pixmap = QtGui.QPixmap(":/Icons/img/icons/activeNozzle.png")
                if not pixmap.isNull():
                    self.tool1Label.setPixmap(pixmap)
                    self.logger.debug("Set tool1Label to activeNozzle.png")
                else:
                    self.logger.error("Failed to load activeNozzle.png pixmap")
                # Note: toolToggleChangeFilamentButton is not defined in this screen
                # if hasattr(self, 'toolToggleChangeFilamentButton'):
                #     self.toolToggleChangeFilamentButton.setChecked(True)
        except Exception as e:
            self.logger.error("Error in HomeScreen.setActiveExtruder: {}".format(e))
            dialog.WarningOk(self, "Error in home_screen.setActiveExtruder: {}".format(e), overlay=True)

    def updateFeedRate(self, rate):
        """Update the feed rate label when feed rate changes."""
        try:
            self.feedRateLabel.setText(f"{rate}%")
        except Exception as e:
            self.logger.error(f"Error updating feed rate label: {e}")

    def updateFlowRate(self, rate):
        """Update the flow rate label when flow rate changes."""
        try:
            self.flowRateLabel.setText(f"{rate}%")
        except Exception as e:
            self.logger.error(f"Error updating flow rate label: {e}")

    # --- New slots for tool state reflection on HomeScreen ---
    def on_tool_states_loaded(self, states: dict):
        m = self.main_window.printer_model
        self._apply_tool("tool0", m.get_bay_state("tool0"))
        self._apply_tool("tool1", m.get_bay_state("tool1"))

    def on_tool_state_changed(self, tool: str, bay: str, data: dict):
        if bay == self.main_window.printer_model.get_default_bay(tool):
            self._apply_tool(tool, data)

    def _apply_tool(self, tool: str, data: dict):
        filament_val = data.get("filament")
        status_val = data.get("status", "Unknown")
        nozzle_val = data.get("nozzle", "Unknown")
        if tool == "tool0":
            lab_f, lab_n = getattr(self, 'tool0LoadedFilament', None), getattr(self, 'tool0LoadedNozzle', None)
        else:
            lab_f, lab_n = getattr(self, 'tool1LoadedFilament', None), getattr(self, 'tool1LoadedNozzle', None)
        try:
            if lab_f:
                display_filament = "-" if status_val == "Empty" else (str(filament_val) if filament_val else "-")
                lab_f.setText(display_filament)
            if lab_n:
                lab_n.setText("-" if nozzle_val == "Unknown" or not nozzle_val else f"{nozzle_val} mm")
        except Exception as e:
            self.logger.debug(f"Failed applying tool UI: {e}")
