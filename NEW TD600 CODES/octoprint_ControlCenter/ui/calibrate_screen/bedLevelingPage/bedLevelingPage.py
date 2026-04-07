import os
from PyQt5 import uic, QtGui
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils.printer_ui_config import is_dual_nozzle_printer
from utils import dialog


logger = get_logger(__name__)

class BedLeveling(QWidget):
    """
    Bed Leveling widget that guides the user through the bed leveling calibration process
    with a multi-step wizard interface.
    """

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.model = main_window.printer_model
        self.octoprint_client = main_window.octoprint_client
        self.logger = get_logger(self.__class__.__name__)  # Using the centralized logger
        self.logger.info("Initializing Bed Leveling screen")

        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "bedLevelingPage.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("BedLeveling UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load BedLeveling UI file: {e}")

        # Initialize the Pages
        self.stackedWidget = self.findChild(QStackedWidget, "stackedWidget")
        self.quickStep1Page = self.findChild(QWidget, "quickStep1Page")
        self.quickStep2Page = self.findChild(QWidget, "quickStep2Page")
        self.quickStep3Page = self.findChild(QWidget, "quickStep3Page")
        self.quickStep4Page = self.findChild(QWidget, "quickStep4Page")

        # Initialize the buttons
        self.quickStep1NextButton = self.findChild(QPushButton, "quickStep1NextButton")
        self.quickStep1CancelButton = self.findChild(QPushButton, "quickStep1CancelButton")
        self.quickStep2NextButton = self.findChild(QPushButton, "quickStep2NextButton")
        self.quickStep2CancelButton = self.findChild(QPushButton, "quickStep2CancelButton")
        self.quickStep3NextButton = self.findChild(QPushButton, "quickStep3NextButton")
        self.quickStep3CancelButton = self.findChild(QPushButton, "quickStep3CancelButton")
        self.quickStep4NextButton = self.findChild(QPushButton, "quickStep4NextButton")
        self.quickStep4CancelButton = self.findChild(QPushButton, "quickStep4CancelButton")

        # Validate UI elements
        check_ui_elements(self, [
            self.stackedWidget, self.quickStep1Page, self.quickStep2Page,
            self.quickStep3Page, self.quickStep4Page,
            self.quickStep1NextButton, self.quickStep1CancelButton, self.quickStep2NextButton,
            self.quickStep2CancelButton,
            self.quickStep3NextButton, self.quickStep3CancelButton, self.quickStep4NextButton,
            self.quickStep4CancelButton
        ], "BedLeveling")

        self.quickStep1NextButton.clicked.connect(self.quickStep2)
        self.quickStep2NextButton.clicked.connect(self.quickStep3)
        self.quickStep3NextButton.clicked.connect(self.quickStep4)
        self.quickStep4NextButton.clicked.connect(self.doneStep)

        self.quickStep1CancelButton.clicked.connect(self.cancelStep)
        self.quickStep2CancelButton.clicked.connect(self.cancelStep)
        self.quickStep3CancelButton.clicked.connect(self.cancelStep)
        self.quickStep4CancelButton.clicked.connect(self.cancelStep)

        self.logger.info("Bed Leveling initialization complete")

    def showEvent(self, event):
        """Reset to quickStep1Page whenever this widget is shown."""
        super().showEvent(event)
        try:
            self.quickStep1()
            self.logger.debug("Reset stacked widget to quickStep1Page on show")
        except Exception as e:
            self.logger.error(f"Error resetting to quickStep1Page: {e}")

    def quickStep1(self):
        """
        Shows welcome message.
        Homes to MAX
        goes to position where leveling screws can be opened
        :return:
        """
        self.logger.info("BedLeveling.quickStep1 started")
        try:
            self.octoprint_client.gcode(command='M104 S200')
            
            # Only heat T1 for dual nozzle printers
            if is_dual_nozzle_printer():
                self.octoprint_client.gcode(command='M104 T1 S200')

            self.octoprint_client.gcode(command='T0')  # Set active tool to t0
            self.octoprint_client.gcode(
                command='M503')  # makes sure internal value of Z offset and Tool offsets are stored before erasing
            self.octoprint_client.gcode(command='M420 S0')  # Disable mesh bed leveling for good measure
            self.stackedWidget.setCurrentWidget(self.quickStep1Page)
            self.octoprint_client.home(['x', 'y', 'z'])
            self.octoprint_client.gcode(command='T0')
            self.octoprint_client.jog(x=40, y=40, absolute=True, speed=2000)
        except Exception as e:
            self.logger.error("Error in BedLeveling.quickStep1: {}".format(e))
            dialog.WarningOk(self, "Error in BedLeveling.quickStep1: {}".format(e), overlay=True)

    def quickStep2(self):
        """
        levels first position (RIGHT)
        :return:
        """
        self.logger.info("BedLeveling.quickStep2 started")
        try:
            self.stackedWidget.setCurrentWidget(self.quickStep2Page)
            self.octoprint_client.jog(
                x=self.main_window.printer_model.calibrationPosition['X1'],
                y=self.main_window.printer_model.calibrationPosition['Y1'],
                absolute=True, speed=10000
            )
            self.octoprint_client.jog(z=0, absolute=True, speed=1500)
            self.movie1 = QtGui.QMovie(
                os.path.join(os.path.dirname(__file__), "resources", "CalibrationPoint1.gif")
            )
            self.movie1.setCacheMode(QtGui.QMovie.CacheNone)
            self.CalibrationPoint1.setMovie(self.movie1)
            self.movie1.start()
        except Exception as e:
            self.logger.error("Error in BedLeveling.quickStep2: {}".format(e))
            dialog.WarningOk(self, "Error in BedLeveling.quickStep2: {}".format(e), overlay=True)
            try:
                self.movie1.stop()
            except:
                pass

    def quickStep3(self):
        """
        levels second leveling position (LEFT)
        """
        self.logger.info("BedLeveling.quickStep3 started")
        try:
            self.stackedWidget.setCurrentWidget(self.quickStep3Page)
            self.octoprint_client.jog(z=10, absolute=True, speed=1500)
            self.octoprint_client.jog(
                x=self.main_window.printer_model.calibrationPosition['X2'],
                y=self.main_window.printer_model.calibrationPosition['Y2'],
                absolute=True, speed=10000
            )
            self.octoprint_client.jog(z=0, absolute=True, speed=1500)
            self.movie1.stop()
            self.movie2 = QtGui.QMovie(
                os.path.join(os.path.dirname(__file__), "resources", "CalibrationPoint2.gif")
            )
            self.movie2.setCacheMode(QtGui.QMovie.CacheNone)
            self.CalibrationPoint2.setMovie(self.movie2)
            self.movie2.start()
        except Exception as e:
            self.logger.error("Error in BedLeveling.quickStep3: {}".format(e))
            dialog.WarningOk(self, "Error in BedLeveling.quickStep3: {}".format(e), overlay=True)
            try:
                self.movie1.stop()
                self.movie2.stop()
            except:
                pass

    def quickStep4(self):
        """
        levels third leveling position  (BACK)
        :return:
        """
        self.logger.info("BedLeveling.quickStep4 started")
        try:
            # sent twice for some reason
            self.stackedWidget.setCurrentWidget(self.quickStep4Page)
            self.octoprint_client.jog(z=10, absolute=True, speed=1500)
            self.octoprint_client.jog(
                x=self.main_window.printer_model.calibrationPosition['X3'],
                y=self.main_window.printer_model.calibrationPosition['Y3'],
                absolute=True, speed=10000
            )
            self.octoprint_client.jog(z=0, absolute=True, speed=1500)
            self.movie2.stop()
            self.movie3 = QtGui.QMovie(
                os.path.join(os.path.dirname(__file__), "resources", "CalibrationPoint3.gif")
            )
            self.movie3.setCacheMode(QtGui.QMovie.CacheNone)
            self.CalibrationPoint3.setMovie(self.movie3)
            self.movie3.start()
        except Exception as e:
            self.logger.error("Error in BedLeveling.quickStep4: {}".format(e))
            dialog.WarningOk(self, "Error in BedLeveling.quickStep4: {}".format(e), overlay=True)
            try:
                self.movie2.stop()
                self.movie3.stop()
            except:
                pass

    def doneStep(self):
        """
        Exits leveling - simplified since dual nozzle offset calibration 
        is now handled by ZToolOffsetWizard
        """
        self.logger.info("BedLeveling.doneStep started")
        try:
            self.octoprint_client.jog(z=4, absolute=True, speed=1500)
            self.octoprint_client.home(['x', 'y', 'z'])

            self.main_window.calibrate_screen.show_calibrate_screen()
            self.octoprint_client.gcode(command='M104 S0')
            
            # Only turn off T1 heater for dual nozzle printers
            if is_dual_nozzle_printer():
                self.octoprint_client.gcode(command='M104 T1 S0')
                
            self.octoprint_client.gcode(command='M84')
            self.octoprint_client.gcode(
                command='M500')  # store eeprom settings to get Z home offset, mesh bed leveling back
        except Exception as e:
            self.logger.error("Error in BedLeveling.doneStep: {}".format(e))
            dialog.WarningOk(self, "Error in BedLeveling.doneStep: {}".format(e), overlay=True)
            try:
                self.movie1.stop()
                self.movie2.stop()
                self.movie3.stop()
            except:
                pass

    def cancelStep(self):
        self.logger.info("BedLeveling.cancelStep started")
        try:
            self.main_window.calibrate_screen.show_calibrate_screen()
            self.octoprint_client.home(['x', 'y', 'z'])
            self.octoprint_client.gcode(command='M104 S0')
            
            # Only turn off T1 heater for dual nozzle printers
            if is_dual_nozzle_printer():
                self.octoprint_client.gcode(command='M104 T1 S0')
                
            self.octoprint_client.gcode(command='M84')
            try:
                self.movie1.stop()
                self.movie2.stop()
                self.movie3.stop()
            except:
                pass
        except Exception as e:
            self.logger.error("Error in BedLeveling.cancelStep: {}".format(e))
            dialog.WarningOk(self, "Error in BedLeveling.cancelStep: {}".format(e), overlay=True)
            try:
                self.movie1.stop()
                self.movie2.stop()
                self.movie3.stop()
            except:
                pass
