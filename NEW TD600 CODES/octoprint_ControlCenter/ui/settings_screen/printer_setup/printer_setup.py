import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QPushButton, QComboBox, QLabel
from PyQt5.QtCore import pyqtSignal
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import dialog
from utils.printer_config_manager import (
    get_available_printers, 
    get_printer_display_name, 
    copy_firmware_files, 
    get_current_printer_selection,
    get_printer_config_manager,
    restore_octoprint_configs
)

logger = get_logger(__name__)


class PrinterSetup(QWidget):
    """
    Printer Setup widget that allows users to select and configure printer types.
    """
    
    # Signal emitted when printer configuration is successfully changed
    printer_changed = pyqtSignal(str)  # printer config filename

    def __init__(self, parent, settings_screen):
        super(PrinterSetup, self).__init__(parent)
        self.mainSettingsWidget = settings_screen  # Reference to the main settings widget
        self.logger = get_logger(self.__class__.__name__)

        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "printer_setup.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("PrinterSetup UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load PrinterSetup UI file: {e}")
            return

        # Initialize UI components using findChild
        self.backButton = self.findChild(QPushButton, "backButton")
        self.printerComboBox = self.findChild(QComboBox, "printerComboBox")
        self.cancelButton = self.findChild(QPushButton, "cancelButton")
        self.setButton = self.findChild(QPushButton, "setButton")
        self.currentPrinterLabel = self.findChild(QLabel, "currentPrinterLabel")
        self.statusLabel = self.findChild(QLabel, "statusLabel")

        # Validate UI components
        check_ui_elements(self, [
            self.backButton,
            self.printerComboBox,
            self.cancelButton,
            self.setButton,
            self.currentPrinterLabel,
            self.statusLabel
        ], "Printer Setup")

        # Connect button signals
        self.backButton.clicked.connect(self.go_back)
        self.cancelButton.clicked.connect(self.cancel_selection)
        self.setButton.clicked.connect(self.apply_printer_selection)

        # Populate printer options
        self.populate_printer_options()
        
        # Update current printer display
        self.update_current_printer_display()
        
        # Check firmware files status
        self.check_firmware_files_status()

    def populate_printer_options(self):
        """Populate the combobox with available printer configurations."""
        try:
            self.printerComboBox.clear()
            
            available_printers = get_available_printers()
            self.logger.debug(f"Available printers: {available_printers}")
            
            if not available_printers:
                self.logger.warning("No printer configurations found")
                self.statusLabel.setText("No printer configurations available")
                self.setButton.setEnabled(False)
                return
            
            # Add printers to combobox with display names
            for printer_name in available_printers:
                display_name = get_printer_display_name(printer_name)
                self.printerComboBox.addItem(display_name, printer_name)
                self.logger.debug(f"Added printer: {printer_name} -> '{display_name}'")
            
            self.logger.debug(f"Combobox populated with {self.printerComboBox.count()} items")
            
            # Set current selection to match the currently active printer
            current_printer = get_current_printer_selection()
            self.logger.debug(f"Current active printer: {current_printer}")
            
            selection_set = False
            if current_printer:
                for i in range(self.printerComboBox.count()):
                    if self.printerComboBox.itemData(i) == current_printer:
                        self.printerComboBox.setCurrentIndex(i)
                        self.logger.info(f"Set combobox to printer: {current_printer}")
                        selection_set = True
                        break
            
            # If no current printer found or failed to set selection, default to first item
            if not selection_set and self.printerComboBox.count() > 0:
                self.printerComboBox.setCurrentIndex(0)
                default_printer = self.printerComboBox.itemData(0)
                self.logger.info(f"Defaulted to first printer: {default_printer}")
            
            self.logger.info(f"Loaded {len(available_printers)} printer configurations")
            self.statusLabel.setText("Ready to configure printer")
            
        except Exception as e:
            self.logger.error(f"Error populating printer options: {e}")
            self.statusLabel.setText("Error loading printer configurations")
            self.setButton.setEnabled(False)

    def update_current_printer_display(self):
        """Update the display showing the currently active printer."""
        try:
            current_printer = get_current_printer_selection()
            if current_printer:
                display_name = get_printer_display_name(current_printer)
                self.currentPrinterLabel.setText(f"Current Printer: {display_name}")
            else:
                self.currentPrinterLabel.setText("Current Printer: Unknown")
        except Exception as e:
            self.logger.error(f"Error updating current printer display: {e}")
            self.currentPrinterLabel.setText("Current Printer: Error")

    def cancel_selection(self):
        """Reset the combobox to the currently active printer and go back."""
        try:
            current_printer = get_current_printer_selection()
            if current_printer:
                for i in range(self.printerComboBox.count()):
                    if self.printerComboBox.itemData(i) == current_printer:
                        self.printerComboBox.setCurrentIndex(i)
                        break
            self.go_back()
        except Exception as e:
            self.logger.error(f"Error canceling selection: {e}")

    def apply_printer_selection(self):
        """Apply the selected printer configuration."""
        try:
            if self.printerComboBox.currentIndex() < 0:
                dialog.WarningOk(self, "Please select a printer configuration.", overlay=True)
                return
            
            selected_printer = self.printerComboBox.currentData()  # This is now just the printer name
            selected_display_name = self.printerComboBox.currentText()
            
            # Confirm the change with the user
            manager = get_printer_config_manager()
            firmware_files = manager.get_firmware_files()
            if not dialog.WarningYesNo(
                self, 
                f"Are you sure you want to change the printer configuration to '{selected_display_name}'?\n\n"
                f"This will copy {len(firmware_files)} configuration files and update printer.cfg.\n"
                "The printer may require a firmware restart.",
                overlay=True
            ):
                return
            
            self.statusLabel.setText("Copying firmware files and applying configuration...")
            self.setButton.setEnabled(False)
            
            # Apply the configuration
            success = copy_firmware_files(selected_printer)
            
            # Also restore OctoPrint configurations for the selected printer
            if success:
                self.statusLabel.setText("Updating OctoPrint configurations...")
                octoprint_success = restore_octoprint_configs(selected_printer)
                if not octoprint_success:
                    self.logger.warning("Failed to restore OctoPrint configs, but Klipper config was successful")
            
            if success:
                # Note: No need to store selection in config store - printer.cfg is the source of truth
                try:
                    if hasattr(self.mainSettingsWidget, 'main_window') and \
                       hasattr(self.mainSettingsWidget.main_window, 'printer_model'):
                        
                        # Reload printer configuration from the new Klipper settings
                        self.mainSettingsWidget.main_window.printer_model.reload_printer_configuration()
                        
                        # Emit signal for other components
                        self.printer_changed.emit(selected_printer)
                        self.logger.info(f"Applied printer configuration: {selected_printer}")
                        
                except Exception as e:
                    self.logger.error(f"Error reloading printer configuration: {e}")
                
                self.statusLabel.setText("Printer configuration applied successfully!")
                self.update_current_printer_display()
                
                # Show restart dialog and restart when OK is pressed
                firmware_files = manager.get_firmware_files()
                restart_msg = (
                    f"Printer configuration changed to '{selected_display_name}'.\n\n"
                    f"Copied {len(firmware_files)} configuration files to Klipper.\n\n"
                    "The printer will restart now for changes to take effect."
                )
                self.restart_printer_system(restart_msg)
                
            else:
                self.statusLabel.setText("Failed to apply printer configuration")
                dialog.WarningOk(
                    self,
                    "Failed to apply printer configuration. Please check the logs for details.",
                    overlay=True
                )
            
            self.setButton.setEnabled(True)
            
        except Exception as e:
            self.logger.error(f"Error applying printer selection: {e}")
            self.statusLabel.setText("Error applying configuration")
            self.setButton.setEnabled(True)
            dialog.WarningOk(
                self,
                f"Error applying printer configuration: {e}",
                overlay=True
            )

    def go_back(self):
        """Return to the main settings screen."""
        try:
            self.mainSettingsWidget.stackedWidget.setCurrentWidget(self.mainSettingsWidget.mainSettingsPage)
            self.logger.info("Returned to main settings screen")
        except Exception as e:
            self.logger.error(f"Error returning to main settings: {e}")

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

    def showEvent(self, event):
        """Refresh data when the screen is shown."""
        super().showEvent(event)
        try:
            self.populate_printer_options()
            self.update_current_printer_display()
            self.check_firmware_files_status()
        except Exception as e:
            self.logger.error(f"Error refreshing printer setup screen: {e}")
    
    def check_firmware_files_status(self):
        """Check and log the status of firmware files in Klipper config directory."""
        try:
            manager = get_printer_config_manager()
            missing_files = manager.get_missing_config_files()
            firmware_files = manager.get_firmware_files()
            
            if missing_files:
                self.logger.warning(f"Missing {len(missing_files)} firmware files in Klipper config: {', '.join(missing_files[:5])}{'...' if len(missing_files) > 5 else ''}")
            else:
                self.logger.info(f"All {len(firmware_files)} firmware files are present in Klipper config")
                
        except Exception as e:
            self.logger.error(f"Error checking firmware files status: {e}")
