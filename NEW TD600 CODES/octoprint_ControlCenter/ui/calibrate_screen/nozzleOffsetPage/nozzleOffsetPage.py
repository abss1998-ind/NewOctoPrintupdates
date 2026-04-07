import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QPushButton, QDoubleSpinBox, QLabel
from PyQt5.QtGui import QPalette, QColor
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import dialog

logger = get_logger(__name__)


class NozzleOffsetPage(QWidget):
    """
    Nozzle Offset configuration page that allows users to adjust and set the
    offset values for the printer's nozzle.
    """

    def __init__(self, main_window):
        super(NozzleOffsetPage, self).__init__()
        self.main_window = main_window
        self.octoprint_client = main_window.octoprint_client
        self.current_nozzle_offset = 0.0

        # Use centralized logger
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing NozzleOffsetPage")

        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "nozzleOffsetPage.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("NozzleOffsetPage UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load NozzleOffsetPage UI file: {e}", exc_info=True)

        # Initialize UI components
        self.nozzleOffsetBackButton = self.findChild(QPushButton, "nozzleOffsetBackButton")
        self.nozzleOffsetSetButton = self.findChild(QPushButton, "nozzleOffsetSetButton")
        self.nozzleOffsetDoubleSpinBox = self.findChild(QDoubleSpinBox, "nozzleOffsetDoubleSpinBox")
        # self.currentNozzleOffsetLabel = self.findChild(QLabel, "currentNozzleOffset_2")

        # Validate UI elements
        check_ui_elements(self, [
            self.nozzleOffsetBackButton, self.nozzleOffsetSetButton,
            self.nozzleOffsetDoubleSpinBox
        ], "Nozzle Offset Page")

        # Connect buttons to their respective methods
        self.nozzleOffsetBackButton.clicked.connect(lambda: self.main_window.calibrate_screen.show_calibrate_screen())
        self.nozzleOffsetSetButton.clicked.connect(
            lambda: self.setZProbeOffset(self.nozzleOffsetDoubleSpinBox.value())
        )

        # # Initialize the current nozzle offset display
        # self.currentNozzleOffsetLabel.setText(f"{self.current_nozzle_offset:.2f} mm")

        # Configure spinbox
        self._configure_spinbox(self.nozzleOffsetDoubleSpinBox)

        # ! Local signal slot connection
        self.main_window.printer_model.z_probe_offset_updated.connect(self.updateEEPROMProbeOffset)


    def updateEEPROMProbeOffset(self, offset):
        """
        Sets the spinbox value to have the value of the Z offset from the printer.
        the value is -ve to be more intuitive.
        :param offset:
        :return:
        """
        logger.info("NozzleOffsetPage.updateEEPROMProbeOffset started")
        try:
            # self.currentNozzleOffsetLabel.setText(str(float(offset)))
            self.nozzleOffsetDoubleSpinBox.setValue(float(offset))
        except Exception as e:
            logger.error("Error in NozzleOffsetPage.updateEEPROMProbeOffset: {}".format(e))
            dialog.WarningOk(self, "Error in NozzleOffsetPage.updateEEPROMProbeOffset: {}".format(e), overlay=True)

    def setZProbeOffset(self, offset):
        """Sets Z Probe offset from spinbox and updates UI accordingly."""
        try:
            rounded_offset = round(float(offset), 2)
            logger.info(f"Setting Z Probe Offset to: {rounded_offset} mm")

            # Send G-code commands
            self.octoprint_client.gcode(command=f'M851 Z{rounded_offset}')
            self.octoprint_client.gcode(command='M500')
            self.octoprint_client.gcode(command='RESTART')

            # # Reset spin box and update UI
            # self.nozzleOffsetDoubleSpinBox.setValue(0)
            # current_offset = float(self.currentNozzleOffsetLabel.text().replace("mm", "").strip()) + rounded_offset
            # self.currentNozzleOffsetLabel.setText(f"{current_offset:.2f} mm")
        except Exception as e:
            logger.error("Error in NozzleOffsetPage.setZProbeOffset: {}".format(e))
            dialog.WarningOk(self, "Error in NozzleOffsetPage.setZProbeOffset: {}".format(e), overlay=True)

    def _configure_spinbox(self, spinbox):
        """Configure the nozzle offset spinbox to be readonly, disabled, and styled."""
        spinbox.lineEdit().setReadOnly(True)
        spinbox.lineEdit().setDisabled(True)
        palette = QPalette()
        palette.setColor(QPalette.Highlight, QColor(40, 40, 40))
        spinbox.lineEdit().setPalette(palette)
        self.logger.debug("Spinbox configured with custom styling")