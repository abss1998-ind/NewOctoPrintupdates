import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QPushButton, QDoubleSpinBox, QStackedWidget
from PyQt5.QtGui import QPalette, QColor
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import dialog


logger = get_logger(__name__)

class ToolOffset(QWidget):
    """
    Tool Offset configuration page that allows users to set the XY and Z offsets
    between multiple extruders for dual-extruder printers.
    """
    def __init__(self, main_window):
        super(ToolOffset, self).__init__()
        self.main_window = main_window
        self.octoprint_client = main_window.octoprint_client
        # Use centralized logger
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing ToolOffset page")

        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "toolOffset.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("ToolOffset UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load ToolOffset UI file: {e}")

    # Initialize UI components
        self.stackedWidget = self.findChild(QStackedWidget, "stackedWidget")
        self.toolOffsetXYPage = self.findChild(QWidget, "toolOffsetXYPage")
        self.toolOffsetZPage = self.findChild(QWidget, "toolOffsetZPage")
        self.toolOffsetXYBackButton = self.findChild(QPushButton, "toolOffsetXYBackButton")
        self.toolOffsetZBackButton = self.findChild(QPushButton, "toolOffsetZBackButton")
        self.toolOffsetXSetButton = self.findChild(QPushButton, "toolOffsetXSetButton")
        self.toolOffsetYSetButton = self.findChild(QPushButton, "toolOffsetYSetButton")
        self.toolOffsetZSetButton = self.findChild(QPushButton, "toolOffsetZSetButton")
        self.toolOffsetXDoubleSpinBox = self.findChild(QDoubleSpinBox, "toolOffsetXDoubleSpinBox")
        self.toolOffsetYDoubleSpinBox = self.findChild(QDoubleSpinBox, "toolOffsetYDoubleSpinBox")
        self.toolOffsetZDoubleSpinBox = self.findChild(QDoubleSpinBox, "toolOffsetZDoubleSpinBox")

        # Configure spinboxes
        spinboxes = [
            self.toolOffsetXDoubleSpinBox,
            self.toolOffsetYDoubleSpinBox,
            self.toolOffsetZDoubleSpinBox
        ]
        for spinbox in spinboxes:
            if spinbox:
                spinbox.lineEdit().setReadOnly(True)
                spinbox.lineEdit().setDisabled(True)
                palette = QPalette()
                palette.setColor(QPalette.Highlight, QColor(40, 40, 40))
                spinbox.lineEdit().setPalette(palette)

    # Validate UI components
        check_ui_elements(self, [
            self.stackedWidget,
            self.toolOffsetXYPage,
            self.toolOffsetZPage,
            self.toolOffsetXYBackButton,
            self.toolOffsetZBackButton,
            self.toolOffsetXSetButton,
            self.toolOffsetYSetButton,
            self.toolOffsetZSetButton,
            self.toolOffsetXDoubleSpinBox,
            self.toolOffsetYDoubleSpinBox,
            self.toolOffsetZDoubleSpinBox
        ], "ToolOffset Page")

    # Connect buttons to their respective methods
        self.toolOffsetXYBackButton.clicked.connect(lambda: self.main_window.calibrate_screen.show_calibrate_screen())
        self.toolOffsetZBackButton.clicked.connect(lambda: self.main_window.calibrate_screen.show_calibrate_screen())
        self.toolOffsetXSetButton.clicked.connect(self.setToolOffsetX)
        self.toolOffsetYSetButton.clicked.connect(self.setToolOffsetY)
        self.toolOffsetZSetButton.clicked.connect(self.setToolOffsetZ)

    # ! Local signal slot connections
        self.main_window.printer_model.tool_offset_data.connect(self.setToolOffset_UI)

        # Set default page
        self.stackedWidget.setCurrentWidget(self.toolOffsetZPage)
        self.logger.debug("Set default page to toolOffsetZPage")

    def showEvent(self, event):
        """Reset to toolOffsetZPage whenever this widget is shown."""
        super().showEvent(event)
        try:
            self.stackedWidget.setCurrentWidget(self.toolOffsetZPage)
            self.logger.debug("Reset stacked widget to toolOffsetZPage on show")
        except Exception as e:
            self.logger.error(f"Error resetting to toolOffsetZPage: {e}")

    def setToolOffsetX(self):
        logger.info("ToolOffset.setToolOffsetX started")
        try:
            self.octoprint_client.gcode(
                command='M218 T1 X{}'.format(round(self.toolOffsetXDoubleSpinBox.value(), 2))
            )  # restore eeprom settings to get Z home offset, mesh bed leveling back
            self.octoprint_client.gcode(command='M500')
            logger.info("X offset set to: {}".format(round(self.toolOffsetXDoubleSpinBox.value(), 2)))
        except Exception as e:
            logger.error("Error in ToolOffset.setToolOffsetX: {}".format(e))
            dialog.WarningOk(self, "Error in ToolOffset.setToolOffsetX: {}".format(e), overlay=True)

    def setToolOffsetY(self):
        logger.info("ToolOffset.setToolOffsetY started")
        try:
            self.octoprint_client.gcode(
                command='M218 T1 Y{}'.format(round(self.toolOffsetYDoubleSpinBox.value(), 2))
            )  # restore eeprom settings to get Z home offset, mesh bed leveling back
            self.octoprint_client.gcode(command='M500')
            self.octoprint_client.gcode(command='M500')
            logger.info("Y offset set to: {}".format(round(self.toolOffsetYDoubleSpinBox.value(), 2)))
        except Exception as e:
            logger.error("Error in ToolOffset.setToolOffsetY: {}".format(e))
            dialog.WarningOk(self, "Error in ToolOffset.setToolOffsetY: {}".format(e), overlay=True)

    def setToolOffsetZ(self):
        logger.info("ToolOffset.setToolOffsetZ started")
        try:
            self.octoprint_client.gcode(
                command='M218 T1 Z{}'.format(round(self.toolOffsetZDoubleSpinBox.value(), 2))
            )  # restore eeprom settings to get Z home offset, mesh bed leveling back
            self.octoprint_client.gcode(command='M500')
            logger.info("Z offset set to: {}".format(round(self.toolOffsetZDoubleSpinBox.value(), 2)))
        except Exception as e:
            logger.error("Error in ToolOffset.setToolOffsetZ: {}".format(e))
            dialog.WarningOk(self, "Error in ToolOffset.setToolOffsetZ: {}".format(e), overlay=True)

    def setToolOffset_UI(self, M218Data):
        logger.info("ToolOffset.setToolOffset started")
        try:
            # if float(M218Data[M218Data.index('X') + 1:].split(' ', 1)[0] ) > 0:
            self.toolOffsetZ = M218Data[M218Data.index('Z') + 1:].split(' ', 1)[0]
            self.toolOffsetX = M218Data[M218Data.index('X') + 1:].split(' ', 1)[0]
            self.toolOffsetY = M218Data[M218Data.index('Y') + 1:].split(' ', 1)[0]
            self.toolOffsetXDoubleSpinBox.setValue(float(self.toolOffsetX))
            self.toolOffsetYDoubleSpinBox.setValue(float(self.toolOffsetY))
            self.toolOffsetZDoubleSpinBox.setValue(float(self.toolOffsetZ))
        except Exception as e:
            logger.error("Error in ToolOffset.setToolOffset: {}".format(e))
            dialog.WarningOk(self, "Error in ToolOffset.setToolOffset: {}".format(e), overlay=True)

