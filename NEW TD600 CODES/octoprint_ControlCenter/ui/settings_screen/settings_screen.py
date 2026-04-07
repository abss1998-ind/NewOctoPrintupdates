import os
import subprocess
import shutil
import glob
from datetime import datetime
import importlib.util
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QVBoxLayout, QScrollArea
from PyQt5.QtGui import QFont
from utils import dialog
from utils.helpers import check_ui_elements, run_async
from utils.logger import get_logger
from utils.dialog import WarningYesNo, WarningOk

# Import sub-UI classes
from ui.settings_screen.software_update.software_update import SoftwareUpdate
from ui.settings_screen.network_settings.network_settings import NetworkSettings
from ui.settings_screen.printer_setup.printer_setup import PrinterSetup

logger = get_logger(__name__)

class SettingsScreen(QWidget):
    def __init__(self, main_window, minimalUI=False):
        super(SettingsScreen, self).__init__()
        self.main_window = main_window
        self.minimalUI = minimalUI
        self.octoprint_client = main_window.octoprint_client

        # Use the centralized logger
        self.logger = get_logger(self.__class__.__name__)

        # Load the UI with proper error handling
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "settings_screen.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("Settings screen UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load settings screen UI file: {e}")
            return

        # Initialize UI components using findChild
        # Container widgets
        self.stackedWidget = self.findChild(QStackedWidget, "mainSettingsStackedWidget")
        self.mainSettingsPage = self.findChild(QWidget, "mainSettingsPage")
        self.scrollArea = self.findChild(QScrollArea, "scrollArea")

        # Button widgets for navigation and actions
        self.backButton = self.findChild(QPushButton, "settingsBackButton")
        self.networkSettingsButton = self.findChild(QPushButton, "networkSettingsButton")
        self.softwareUpdateButton = self.findChild(QPushButton, "softwareUpdateButton")
        self.printerSetupButton = self.findChild(QPushButton, "printerSetupButton")
        self.restorePrintSettingsButton = self.findChild(QPushButton, "restorePrintSettingsButton")
        self.saveLogsToUSBButton = self.findChild(QPushButton, "saveLogsToUSBButton")
        self.restoreFactoryDefaultsButton = self.findChild(QPushButton, "restoreFactoryDefaultsButton")
        self.restartButton = self.findChild(QPushButton, "restartButton")


        # Validate UI components using simplified check_ui_elements function
        check_ui_elements(self, [
            self.stackedWidget,
            self.mainSettingsPage,
            self.scrollArea,
            self.backButton,
            self.networkSettingsButton,
            self.softwareUpdateButton,
            self.printerSetupButton,
            self.restorePrintSettingsButton,
            self.saveLogsToUSBButton,
            self.restoreFactoryDefaultsButton,
            self.restartButton
            ], "Settings Screen")

        # Connect buttons to their respective functions directly
        self.backButton.clicked.connect(lambda: self.main_window.switch_to_menu_screen())
        self.networkSettingsButton.clicked.connect(self.navigate_to_network_settings)
        self.softwareUpdateButton.clicked.connect(self.navigate_to_software_update)
        self.printerSetupButton.clicked.connect(self.navigate_to_printer_setup)
        self.restorePrintSettingsButton.clicked.connect(self.restore_print_settings)
        self.saveLogsToUSBButton.clicked.connect(self.save_logs_to_usb)
        self.restoreFactoryDefaultsButton.clicked.connect(self.restore_factory_defaults)
        self.restartButton.clicked.connect(self.restart_system)

        # Initialize all sub-screens
        self.screens = {}
        self._initialize_sub_screens()

        # Set the default page in stacked widget
        self.stackedWidget.setCurrentWidget(self.mainSettingsPage)
        self.logger.debug("Set default page to mainSettingsPage")


    def showEvent(self, event):
        """Reset to mainSettingsPage whenever this widget is shown from main window navigation."""
        super().showEvent(event)
        try:
            self.stackedWidget.setCurrentWidget(self.mainSettingsPage)
            self.logger.debug("Reset stacked widget to mainSettingsPage on show")
        except Exception as e:
            self.logger.error(f"Error resetting to mainSettingsPage: {e}")

    def tellAndReboot(self, msg="Rebooting...", overlay=True):
        if dialog.WarningOk(self, msg, overlay=overlay):
            os.system('sudo reboot now')
            return True
        return False

    def askAndReboot(self, msg="Are you sure you want to reboot?", overlay=True):
        if dialog.WarningYesNo(self, msg, overlay=overlay):
            os.system('sudo reboot now')
            return True
        return False

    def restore_print_settings(self):
        """Restore the print settings to their default values for the currently configured printer."""
        self.logger.info("Restoring print settings to default values.")

        try:
            # Import the required modules for printer configuration
            from utils.printer_config_manager import (
                get_current_printer_selection,
                get_printer_display_name,
                copy_firmware_files,
                get_printer_config_manager,
                restore_octoprint_configs
            )
            
            # Check if a printer is currently configured
            current_printer = get_current_printer_selection()
            
            if not current_printer:
                # No printer configured - redirect to printer setup
                self.logger.warning("No printer configured, redirecting to printer setup")
                if dialog.WarningYesNo(
                    self,
                    "No printer configuration found!\n\n"
                    "You need to configure a printer before restoring print settings.\n"
                    "Would you like to configure a printer now?",
                    overlay=True
                ):
                    # Navigate to printer setup screen
                    self.navigate_to_printer_setup()
                else:
                    self.logger.info("User chose not to configure printer")
                return
            
            # Get printer display name for user-friendly dialog
            printer_display_name = get_printer_display_name(current_printer)
            manager = get_printer_config_manager()
            firmware_files = manager.get_firmware_files()
            
            # Confirm restoration with user
            if dialog.WarningYesNo(
                self,
                f"Are you sure you want to restore default print settings for '{printer_display_name}'?\n\n"
                f"This will:\n"
                f"• Copy {len(firmware_files)} default configuration files\n"
                f"• Reset printer firmware settings (M502/M500)\n"
                f"• Erase bed leveling data and offsets\n"
                f"• Restart Klipper firmware\n\n"
                f"Warning: All calibration data will be lost!",
                overlay=True
            ):
                self.logger.info(f"User confirmed restoration of print settings for {current_printer}")
                
                # Use the same system as printer setup wizard to restore files
                self.logger.info(f"Copying firmware files for {current_printer}...")
                success = copy_firmware_files(current_printer)
                
                # Also restore OctoPrint configurations
                if success:
                    self.logger.info("Restoring OctoPrint configurations...")
                    octoprint_success = restore_octoprint_configs(current_printer)
                    if not octoprint_success:
                        self.logger.warning("Failed to restore OctoPrint configs, but Klipper config was successful")
                
                if success:
                    self.logger.info("Firmware files copied successfully, executing printer reset commands")
                    
                    # Reset printer firmware settings (same as before)
                    try:
                        self.octoprint_client.gcode(command='M502')  # Load factory defaults
                        self.octoprint_client.gcode(command='M500')  # Save settings to EEPROM
                        self.octoprint_client.gcode(command='FIRMWARE_RESTART')  # Restart Klipper
                        
                        self.logger.info("Print settings restoration completed successfully")
                        
                        # Show success message with restart dialog
                        restart_msg = (
                            f"Print settings for '{printer_display_name}' have been restored to defaults.\n\n"
                            f"Configuration files have been refreshed and firmware settings reset.\n\n"
                            "The printer will restart now for changes to take effect."
                        )
                        self.restart_printer_system(restart_msg)
                        
                    except Exception as e:
                        self.logger.error(f"Error executing printer reset commands: {e}")
                        dialog.WarningOk(
                            self, 
                            f"Files restored but failed to reset printer firmware: {e}\n"
                            "Please manually restart the printer.",
                            overlay=True
                        )
                        
                else:
                    self.logger.error("Failed to copy firmware files")
                    dialog.WarningOk(
                        self,
                        "Failed to restore print settings. Please check the logs for details.",
                        overlay=True
                    )
            else:
                self.logger.info("User cancelled print settings restoration")
                
        except Exception as e:
            self.logger.error(f"Error in restore_print_settings: {e}")
            dialog.WarningOk(self, f"Error restoring print settings: {e}", overlay=True)

    def restart_printer_system(self, msg="Printer configuration applied successfully!\n\nThe printer needs to restart for changes to take effect.", overlay=True):
        """Show restart dialog and restart the printer system when OK is pressed."""
        try:
            # Use WarningOk which only has an OK button - when clicked, restart immediately
            if dialog.WarningOk(self, msg, overlay=overlay):
                self.logger.info("User confirmed printer restart - restarting now")
                # Restart the printer system
                os.system('sudo reboot now')
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error during printer restart: {e}")
            dialog.WarningOk(self, f"Error during restart: {e}", overlay=True)
            return False

    def restore_factory_defaults(self):
        """Restore the system to factory default settings."""
        self.logger.info("Restoring system to factory default settings.")

        try:
            from utils.printer_config_manager import (
                get_current_printer_selection,
                get_printer_config_manager,
                restore_octoprint_configs
            )
            
            if dialog.WarningYesNo(self,
                                   "Are you sure you want to restore machine state to factory defaults?\nWarning: Doing so will also reset printer profiles, WiFi & Ethernet config.",
                                   overlay=True):
                
                # Get current printer selection to restore appropriate configs
                current_printer = get_current_printer_selection()
                if not current_printer:
                    current_printer = "DRAGON_400"  # Default fallback
                    self.logger.warning(f"No current printer found, using default: {current_printer}")
                
                self.logger.info(f"Restoring factory defaults for printer: {current_printer}")
                
                # Use the enhanced config manager to restore all settings
                manager = get_printer_config_manager()
                success = manager.restore_octoprint_configs(current_printer)
                
                if success:
                    self.logger.info("Factory defaults restored successfully")
                    self.tellAndReboot("Settings restored. Rebooting...")
                else:
                    self.logger.error("Failed to restore some factory default settings")
                    # # Fallback to old method for critical system files using absolute paths
                    # config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
                    # os.system(f'sudo cp -f "{config_dir}/dhcpcd.conf" /etc/dhcpcd.conf')
                    # os.system(f'sudo cp -f "{config_dir}/wpa_supplicant.conf" /etc/wpa_supplicant/wpa_supplicant.conf')
                    self.tellAndReboot("Partial settings restored. Rebooting...")
                    
        except Exception as e:
            self.logger.error("Error in SettingsScreen.restoreFactoryDefaults: {}".format(e))
            dialog.WarningOk(self, "Error in SettingsScreen.restoreFactoryDefaults: {}".format(e), overlay=True)

    def restart_system(self):
        """Restart the system."""
        self.logger.info("Restarting the system.")
        # Add logic to restart the system
        try:
            if WarningYesNo(self, "Are you sure you want to restart the system?", overlay=True):
                self.logger.info("User confirmed reboot")
                os.system("sudo reboot")

            else:
                self.logger.info("User cancelled reboot")
        except Exception as e:
            self.logger.error(f"Error during restart: {e}")
            WarningOk(self, f"Error during restart: {e}", overlay=True)

    def save_logs_to_usb(self):
        """Save OctoPrint and Klipper logs to connected USB drive."""
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QTimer
        
        self.logger.info("Save logs to USB initiated")
        
        # Show loading dialog - will be shown and hidden properly
        loading_dialog = dialog.LoadingDialog(
            self,
            "Saving logs to USB drive...\n\nPlease wait, this may take a moment."
        )
        
        # Give the dialog time to render before blocking operations
        QApplication.processEvents()
        QApplication.processEvents()  # Double process to ensure rendering
        
        try:
            # Check if USB drive is connected and accessible
            usb_path = "/media/usb0"
            
            # First check if mount point exists
            if not os.path.exists(usb_path):
                self.logger.warning("USB mount point not found")
                loading_dialog.hide()
                del loading_dialog
                QApplication.processEvents()
                dialog.WarningOk(
                    self,
                    "USB drive not detected!\n\n"
                    "Please insert a USB drive and try again."
                )
                return
            
            # Check if something is actually mounted at the USB path
            try:
                # Try to list contents to verify USB is accessible  
                subprocess.check_output(["ls", usb_path], stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError:
                self.logger.warning("USB drive not accessible")
                loading_dialog.hide()
                del loading_dialog
                QApplication.processEvents()
                dialog.WarningOk(
                    self,
                    "USB drive not accessible!\n\n"
                    "Please ensure the USB drive is properly connected and try again."
                )
                return
                
            # Create logs directory on USB with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            logs_dir = os.path.join(usb_path, f"printer_logs_{timestamp}")
            
            try:
                os.makedirs(logs_dir, exist_ok=True)
                self.logger.info(f"Created logs directory: {logs_dir}")
            except Exception as e:
                self.logger.error(f"Failed to create logs directory: {e}")
                loading_dialog.hide()
                del loading_dialog
                QApplication.processEvents()
                dialog.WarningOk(
                    self,
                    f"Failed to create logs directory on USB:\n{e}\n\n"
                    "The USB drive may be read-only or full."
                )
                return
            
            copied_files = []
            skipped_files = []
            
            # Define log file paths to copy
            log_paths = [
                # Current Klipper log
                "/tmp/klippy.log",
                # Alternative Klipper log location
                "/home/pi/.octoprint/logs"
            ]
            
            for log_path in log_paths:
                try:
                    if os.path.exists(log_path):
                        if os.path.isfile(log_path):
                            # Copy single log file
                            filename = os.path.basename(log_path)
                            dest_path = os.path.join(logs_dir, filename)
                            shutil.copy2(log_path, dest_path)
                            copied_files.append(filename)
                            self.logger.info(f"Copied log file: {filename}")
                            
                        elif os.path.isdir(log_path):
                            # Copy all log files from directory
                            log_files = glob.glob(os.path.join(log_path, "*.log"))
                            if log_files:
                                octoprint_dir = os.path.join(logs_dir, "octoprint_logs")
                                os.makedirs(octoprint_dir, exist_ok=True)
                                
                                for log_file in log_files:
                                    filename = os.path.basename(log_file)
                                    dest_path = os.path.join(octoprint_dir, filename)
                                    shutil.copy2(log_file, dest_path)
                                    copied_files.append(f"octoprint_logs/{filename}")
                                    self.logger.info(f"Copied OctoPrint log: {filename}")
                    else:
                        skipped_files.append(log_path)
                        self.logger.debug(f"Log path not found, skipping: {log_path}")
                        
                except Exception as e:
                    self.logger.error(f"Error copying log from {log_path}: {e}")
                    skipped_files.append(f"{log_path} (Error: {str(e)})")
            
            # Create a summary file
            try:
                summary_path = os.path.join(logs_dir, "log_collection_summary.txt")
                with open(summary_path, 'w') as f:
                    f.write(f"Log Collection Summary\n")
                    f.write(f"{'=' * 40}\n")
                    f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Collection Directory: {logs_dir}\n\n")
                    
                    f.write(f"Successfully Copied Files ({len(copied_files)}):\n")
                    for file in copied_files:
                        f.write(f"  ✓ {file}\n")
                    
                    if skipped_files:
                        f.write(f"\nSkipped/Failed Files ({len(skipped_files)}):\n")
                        for file in skipped_files:
                            f.write(f"  ✗ {file}\n")
                
                self.logger.info("Created log collection summary")
                
            except Exception as e:
                self.logger.error(f"Failed to create summary file: {e}")
            
            # Hide and delete loading dialog before showing results
            loading_dialog.hide()
            del loading_dialog
            QApplication.processEvents()
            
            # Show success message (NO OVERLAY to prevent UI blocking)
            if copied_files:
                message = (
                    f"Successfully saved logs to USB drive!\n\n"
                    f"Location: printer_logs_{timestamp}/\n"
                    f"Files copied: {len(copied_files)}\n"
                )
                if skipped_files:
                    message += f"Files skipped: {len(skipped_files)}\n"
                    message += "\nSee log_collection_summary.txt for details."
                
                dialog.WarningOk(self, message)
                self.logger.info(f"Log collection completed successfully. {len(copied_files)} files copied.")
            else:
                dialog.WarningOk(
                    self,
                    "No log files were found to copy.\n\n"
                    "This may indicate that the log paths are different or logs haven't been created yet.\n"
                    "Check log_collection_summary.txt on the USB drive for details."
                )
                self.logger.warning("No log files found to copy")
                
        except Exception as e:
            self.logger.error(f"Error in save_logs_to_usb: {e}")
            try:
                loading_dialog.hide()
                del loading_dialog
            except:
                pass
            QApplication.processEvents()
            dialog.WarningOk(
                self,
                f"Error saving logs to USB:\n{e}"
            )

    def _initialize_sub_screens(self):
        """Initialize all settings sub-screens"""
        try:
            # Create instances of each sub-screen
            self.screens["network_settings"] = NetworkSettings(self, self)
            self.screens["software_update"] = SoftwareUpdate(self, self)
            self.screens["printer_setup"] = PrinterSetup(self, self)

            # Add each screen to the stacked widget
            for name, screen in self.screens.items():
                self.stackedWidget.addWidget(screen)
                self.logger.info(f"Added {name} screen to settings stacked widget")
                
            # Connect printer setup signal if available
            if "printer_setup" in self.screens:
                self.screens["printer_setup"].printer_changed.connect(self._on_printer_changed)
                
        except Exception as e:
            self.logger.exception(f"Error initializing sub-screens: {e}")

    def navigate_to_network_settings(self):
        """Open the Network Settings screen."""
        self.logger.info("Navigating to Network Settings screen")
        network_settings_screen = self.screens.get("network_settings")
        self.stackedWidget.setCurrentWidget(network_settings_screen)
        self.logger.info("Navigated to network_settings")

    def navigate_to_software_update(self):
        """Open the Software Update screen and display version info."""
        self.logger.info("Navigating to Software Update screen")
        software_update_screen = self.screens.get("software_update")
        software_update_screen.displayVersionInfo()
        self.stackedWidget.setCurrentWidget(software_update_screen)
        self.logger.info("Navigated to software_update")

    def navigate_to_printer_setup(self):
        """Open the Printer Setup screen."""
        self.logger.info("Navigating to Printer Setup screen")
        printer_setup_screen = self.screens.get("printer_setup")
        self.stackedWidget.setCurrentWidget(printer_setup_screen)
        self.logger.info("Navigated to printer_setup")

    def _on_printer_changed(self, printer_config):
        """Handle printer configuration change."""
        self.logger.info(f"Printer configuration changed to: {printer_config}")
        # Optionally notify other components or trigger additional actions
