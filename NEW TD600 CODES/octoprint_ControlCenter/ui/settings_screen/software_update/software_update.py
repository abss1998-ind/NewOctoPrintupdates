import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QListWidget, QTextEdit
from PyQt5.QtCore import Qt
from utils.helpers import check_ui_elements
from utils import dialog
from utils.logger import get_logger

logger = get_logger(__name__)

class SoftwareUpdate(QWidget):
    """
    Software Update widget that allows users to check for and perform
    software updates on the printer's firmware and system.
    """

    def __init__(self, parent, settings_screen):
        super(SoftwareUpdate, self).__init__(parent)
        self.mainSettingsWidget = settings_screen  # Reference to the main settings widget
        self.octoprint_client = settings_screen.octoprint_client

        # Set up logger
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing SoftwareUpdate screen")

        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "software_update.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("SoftwareUpdate UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load SoftwareUpdate UI file: {e}")

        # Initialize UI components
        # Navigation buttons
        self.softwareUpdateBackButton = self.findChild(QPushButton, "softwareUpdateBackButton")

        # Action buttons
        self.performUpdateButton = self.findChild(QPushButton, "performUpdateButton")

        # UI containers and pages
        self.stackedWidget = self.findChild(QStackedWidget, "stackedWidget")
        self.OTAUpdatePage = self.findChild(QWidget, "OTAUpdatePage")
        self.softwareUpdateProgressPage = self.findChild(QWidget, "softwareUpdateProgressPage")

        # UI content elements
        self.updateListWidget = self.findChild(QListWidget, "updateListWidget")
        self.logTextEdit = self.findChild(QTextEdit, "logTextEdit")

        # Check if UI elements exist and report missing ones
        # Use a simple list of UI elements instead of a dictionary
        check_ui_elements(self, [
            self.softwareUpdateBackButton,
            self.performUpdateButton,
            self.stackedWidget,
            self.OTAUpdatePage,
            self.softwareUpdateProgressPage,
            self.updateListWidget,
            self.logTextEdit
        ], "SoftwareUpdate")

        # Connect buttons to their respective functions
        self.softwareUpdateBackButton.clicked.connect(self.go_back_to_settings_screen)
        self.performUpdateButton.clicked.connect(
            lambda: self.octoprint_client.performSoftwareUpdate()
        )

        # Set the default page in stacked widget
        self.stackedWidget.setCurrentWidget(self.OTAUpdatePage)

        # ! LOCAL SIGNAL AND SLOT CONNECTIONS:
        self.mainSettingsWidget.main_window.printer_model.update_started_signal.connect(self.softwareUpdateProgress)
        self.mainSettingsWidget.main_window.printer_model.update_log_signal.connect(self.softwareUpdateProgressLog)
        self.mainSettingsWidget.main_window.printer_model.update_log_result_signal.connect(self.softwareUpdateResult)
        self.mainSettingsWidget.main_window.printer_model.update_failed_signal.connect(self.updateFailed)

    def showEvent(self, event):
        """Reset to OTAUpdatePage whenever this widget is shown."""
        super().showEvent(event)
        try:
            self.stackedWidget.setCurrentWidget(self.OTAUpdatePage)
            self.logger.debug("Reset stacked widget to OTAUpdatePage on show")
        except Exception as e:
            self.logger.error(f"Error resetting to OTAUpdatePage: {e}")

    def go_back_to_settings_screen(self):
        """Return to the settings screen."""
        self.logger.info("Back to settings screen button clicked")
        self.mainSettingsWidget.stackedWidget.setCurrentWidget(self.mainSettingsWidget.mainSettingsPage)
        self.logger.info("Navigated back to settings screen")

    def update_software(self):
        """Update the software."""
        self.logger.info("Updating software...")

        self.stackedWidget.setCurrentWidget(self.softwareUpdateProgressPage)
        self.logger.debug("Switched to software update progress page")

        self.logTextEdit.append("Software update in progress...")
        self.logger.debug("Added log message to text edit")

        # Actual implementation would include code to:
        # 1. Check for network connectivity
        # 2. Download updates
        # 3. Verify downloaded packages
        # 4. Apply updates
        # 5. Restart system if necessary

    def softwareUpdateProgress(self, data):
        self.logger.info("SoftwareUpdate.softwareUpdateProgress started")
        try:
            # First, ensure we're visible in the main application
            # Navigate to settings screen if not already there
            if self.mainSettingsWidget.main_window.current_screen != self.mainSettingsWidget:
                # Switch to settings screen first
                self.mainSettingsWidget.main_window.switch_screen(self.mainSettingsWidget)
            
            # Then ensure software update screen is visible within settings
            self.mainSettingsWidget.stackedWidget.setCurrentWidget(self)
            
            # Finally, show the progress page within software update screen
            self.stackedWidget.setCurrentWidget(self.softwareUpdateProgressPage)
            self.logTextEdit.setTextColor(Qt.red)
            self.logTextEdit.append("---------------------------------------------------------------\n"
                                    "Updating " + data["name"] + " to " + data["version"] + "\n"
                                                                                            "---------------------------------------------------------------")
        except Exception as e:
            self.logger.error("Error in SoftwareUpdate.softwareUpdateProgress: {}".format(e))
            dialog.WarningOk(self, "Error in SoftwareUpdate.softwareUpdateProgress: {}".format(e), overlay=True)

    def softwareUpdateProgressLog(self, data):
        self.logger.info("SoftwareUpdate.softwareUpdateProgressLog started")
        try:
            self.logTextEdit.setTextColor(Qt.white)
            for line in data:
                self.logTextEdit.append(line["line"])

        except Exception as e:
            self.logger.error("Error in SoftwareUpdate.softwareUpdateProgressLog: {}".format(e))
            dialog.WarningOk(self, "Error in SoftwareUpdate.softwareUpdateProgressLog: {}".format(e), overlay=True)

    def updateFailed(self, data):
        self.logger.info("SoftwareUpdate.updateFailed started")
        try:
            self.stackedWidget.setCurrentWidget(self.OTAUpdatePage)
            messageText = (data["name"] + " failed to update\n")
            if dialog.WarningOkCancel(self, messageText, overlay=True):
                pass
        except Exception as e:
            self.logger.error("Error in SoftwareUpdate.updateFailed: {}".format(e))
            dialog.WarningOk(self, "Error in SoftwareUpdate.updateFailed: {}".format(e), overlay=True)

    def softwareUpdateResult(self, data):
        self.logger.info("SoftwareUpdate.softwareUpdateResult started")
        try:
            messageText = ""
            for item in data:
                messageText += item + ": " + data[item][0] + ".\n"
            messageText += "Restart required"
            self.askAndReboot(messageText)
        except Exception as e:
            self.logger.error("Error in SoftwareUpdate.softwareUpdateResult: {}".format(e))
            dialog.WarningOk(self, "Error in SoftwareUpdate.softwareUpdateResult: {}".format(e), overlay=True)

    def displayVersionInfo(self):
        """
        Displays the version information for octoprint plugins
        """
        self.logger.info("SoftwareUpdate.displayVersionInfo started")
        try:
            self.updateListWidget.clear()
            updateAvailable = False
            self.performUpdateButton.setDisabled(True)

            # Firmware version on the MKS https://github.com/FracktalWorks/OctoPrint-JuliaFirmwareUpdater
            # self.updateListWidget.addItem(self.getFirmwareVersion())

            data = self.octoprint_client.getSoftwareUpdateInfo()
            if data:
                for item in data["information"]:
                    # print(item)
                    plugin = data["information"][item]
                    info = u'\u2713' if not plugin["updateAvailable"] else u"\u2717"  # icon
                    info += plugin["displayName"] + "  " + plugin["displayVersion"] + "\n"
                    info += "   Available: "
                    if "information" in plugin and "remote" in plugin["information"] and \
                            plugin["information"]["remote"]["value"] is not None:
                        info += plugin["information"]["remote"]["value"]
                    else:
                        info += "Unknown"
                    self.updateListWidget.addItem(info)

                    if plugin["updateAvailable"]:
                        updateAvailable = True

                    # if not updatable:
                    #     self.updateListWidget.addItem(u'\u2713' + data["information"][item]["displayName"] +
                    #                                   "  " + data["information"][item]["displayVersion"] + "\n"
                    #                                   + "   Available: " +
                    #                                   )
                    # else:
                    #     updateAvailable = True
                    #     self.updateListWidget.addItem(u"\u2717" + data["information"][item]["displayName"] +
                    #                                   "  " + data["information"][item]["displayVersion"] + "\n"
                    #                                   + "   Available: " +
                    #                                   data["information"][item]["information"]["remote"]["value"])
            if updateAvailable:
                self.performUpdateButton.setDisabled(False)
            self.stackedWidget.setCurrentWidget(self.OTAUpdatePage)
        except Exception as e:
            self.logger.error("Error in SoftwareUpdate.displayVersionInfo: {}".format(e))
            dialog.WarningOk(self, "Error in SoftwareUpdate.displayVersionInfo: {}".format(e), overlay=True)

    def askAndReboot(self, msg="Software update successful, press OK to reboot.", overlay=True):
        """Show success message and reboot the system when OK is pressed."""
        self.logger.info("SoftwareUpdate.askAndReboot started")
        try:
            dialog.WarningOk(self, msg, overlay=overlay)
            self.logger.info("User pressed OK, proceeding with reboot after software update")
            os.system('sudo reboot now')
            return True
        except Exception as e:
            self.logger.error(f"Error during askAndReboot: {e}")
            dialog.WarningOk(self, f"Error during askAndReboot: {e}", overlay=True)
            return False