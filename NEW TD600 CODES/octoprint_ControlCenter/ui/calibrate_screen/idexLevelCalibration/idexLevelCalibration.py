import os
from PyQt5 import uic, QtGui, QtCore
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QLabel
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import dialog

logger = get_logger(__name__)

class IdexLevelCalibration(QWidget):
    """
    IDEX (Independent Dual Extruder) Level Calibration widget that guides the user
    through a multi-step calibration process for aligning the dual extruders.
    """
    def __init__(self, main_window):
        super(IdexLevelCalibration, self).__init__()
        self.main_window = main_window
        self.octoprint_client = main_window.octoprint_client
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing IDEX Level Calibration screen")

        # Load the .ui file
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "idexLevelCalibration.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("IdexLevelCalibration UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load IdexLevelCalibration UI file: {e}")

        # Initialize UI elements
        self.stacked_widget = self.findChild(QStackedWidget, "stackedWidget")
        # Ensure compatibility with methods using self.stackedWidget
        self.stackedWidget = self.stacked_widget
        self.idexConfigStep1Page = self.findChild(QWidget, "idexConfigStep1Page")
        self.idexConfigStep2Page = self.findChild(QWidget, "idexConfigStep2Page")
        self.idexConfigStep3Page = self.findChild(QWidget, "idexConfigStep3Page")
        self.idexConfigStep4Page = self.findChild(QWidget, "idexConfigStep4Page")
        self.idexConfigStep5Page = self.findChild(QWidget, "idexConfigStep5Page")

        self.idexConfigStep1NextButton = self.findChild(QPushButton, "idexConfigStep1NextButton")
        self.idexConfigStep2NextButton = self.findChild(QPushButton, "idexConfigStep2NextButton")
        self.idexConfigStep3NextButton = self.findChild(QPushButton, "idexConfigStep3NextButton")
        self.idexConfigStep4NextButton = self.findChild(QPushButton, "idexConfigStep4NextButton")
        self.idexConfigStep5NextButton = self.findChild(QPushButton, "idexConfigStep5NextButton")

        self.idexConfigStep1CancelButton = self.findChild(QPushButton, "idexConfigStep1CancelButton")
        self.idexConfigStep2CancelButton = self.findChild(QPushButton, "idexConfigStep2CancelButton")
        self.idexConfigStep3CancelButton = self.findChild(QPushButton, "idexConfigStep3CancelButton")
        self.idexConfigStep4CancelButton = self.findChild(QPushButton, "idexConfigStep4CancelButton")
        self.idexConfigStep5CancelButton = self.findChild(QPushButton, "idexConfigStep5CancelButton")

        # Renamed UI elements
        self.CalibrationPoint1 = self.findChild(QLabel, "CalibrationPoint1")
        self.CalibrationPoint2 = self.findChild(QLabel, "CalibrationPoint2")
        self.CalibrationPoint3 = self.findChild(QLabel, "CalibrationPoint3")
        self.NozzleLevel1 = self.findChild(QLabel, "NozzleLevel1")
        self.NozzleLevel2 = self.findChild(QLabel, "NozzleLevel2")

        self.moveZMinusButton = self.findChild(QPushButton, "moveZMinusButton")
        self.moveZPlusButton = self.findChild(QPushButton, "moveZPlusButton")

        # Validate UI elements
        check_ui_elements(self, [
            self.idexConfigStep1Page, self.idexConfigStep2Page, self.idexConfigStep3Page, self.idexConfigStep4Page, self.idexConfigStep5Page,
            self.idexConfigStep1NextButton, self.idexConfigStep2NextButton, self.idexConfigStep3NextButton, self.idexConfigStep4NextButton, self.idexConfigStep5NextButton,
            self.idexConfigStep1CancelButton, self.idexConfigStep2CancelButton, self.idexConfigStep3CancelButton, self.idexConfigStep4CancelButton, self.idexConfigStep5CancelButton,
        ], "IDEX Level Calibration")

        # Connect buttons to their respective functions
        self.idexConfigStep1NextButton.clicked.connect(self.idexConfigStep2)
        self.idexConfigStep2NextButton.clicked.connect(self.idexConfigStep3)
        self.idexConfigStep3NextButton.clicked.connect(self.idexConfigStep4)
        self.idexConfigStep4NextButton.clicked.connect(self.idexConfigStep5)
        self.idexConfigStep5NextButton.clicked.connect(self.idexDoneStep)

        self.idexConfigStep1CancelButton.clicked.connect(self.idexCancelStep)
        self.idexConfigStep2CancelButton.clicked.connect(self.idexCancelStep)
        self.idexConfigStep3CancelButton.clicked.connect(self.idexCancelStep)
        self.idexConfigStep4CancelButton.clicked.connect(self.idexCancelStep)
        self.idexConfigStep5CancelButton.clicked.connect(self.idexCancelStep)

        # Z jog buttons (renamed)
        self.moveZMinusButton.pressed.connect(lambda: self.octoprint_client.jog(z=-0.1))
        self.moveZPlusButton.pressed.connect(lambda: self.octoprint_client.jog(z=0.1))


    def showEvent(self, event):
        """Reset to the first step when the widget is shown and ensure GIF is loaded."""
        super().showEvent(event)
        try:
            self.idexConfigStep1()
            self.logger.info("IdexLevelCalibration showEvent: Reset to idexConfigStep1Page")
        except Exception as e:
            self.logger.error(f"Error in IdexLevelCalibration showEvent: {e}")

    def idexConfigStep1(self):
        """
        Shows welcome message.
        Welcome Page, Give Info. Unlock nozzle and push down
        :return:
        """
        logger.info("IdexLevelCalibration.idexConfigStep1 started")
        try:
            self.octoprint_client.gcode(command='M503')  # Gets old tool offset position
            self.octoprint_client.gcode(command='M218 T1 Z0')  # set nozzle tool offsets to 0
            self.octoprint_client.gcode(command='M104 S200')
            self.octoprint_client.gcode(command='M104 T1 S200')
            self.octoprint_client.home(['x', 'y', 'z'])
            self.octoprint_client.gcode(command='G1 X10 Y10 Z20 F5000')
            self.octoprint_client.gcode(command='T0')  # Set active tool to t0
            self.octoprint_client.gcode(command='M420 S0')  # Dissable mesh bed leveling for good measure
            self.stackedWidget.setCurrentWidget(self.idexConfigStep1Page)
            self.movie1 = QtGui.QMovie(
                os.path.join(os.path.dirname(__file__), "resources", "Nozzlelevel1.gif")
            )
            self.movie1.setCacheMode(QtGui.QMovie.CacheNone)  # Avoid loading entire GIF into memory
            self.NozzleLevel1.setMovie(self.movie1)
            self.movie1.start()
        except Exception as e:
            logger.error("Error in IdexLevelCalibration.idexConfigStep1: {}".format(e))
            dialog.WarningOk(self, "Error in IdexLevelCalibration.idexConfigStep1: {}".format(e), overlay=True)
            try:
                self.movie1.stop()
            except:
                pass

    def idexConfigStep2(self):
        """
        levels first position (RIGHT)
        :return:
        """
        logger.info("IdexLevelCalibration.idexConfigStep2 started")
        try:
            self.stackedWidget.setCurrentWidget(self.idexConfigStep2Page)
            self.octoprint_client.jog(
                x=self.main_window.printer_model.calibrationPosition['X1'],
                y=self.main_window.printer_model.calibrationPosition['Y1'],
                absolute=True, speed=10000
            )
            self.octoprint_client.jog(z=0, absolute=True, speed=1500)
            self.movie1.stop()
            self.movie2 = QtGui.QMovie(
                os.path.join(os.path.dirname(__file__), "resources", "CalibrationPoint1.gif")
            )
            self.movie2.setCacheMode(QtGui.QMovie.CacheNone)  # Avoid loading entire GIF into memory
            self.CalibrationPoint1.setMovie(self.movie2)
            self.movie2.start()
        except Exception as e:
            logger.error("Error in IdexLevelCalibration.idexConfigStep2: {}".format(e))
            dialog.WarningOk(self, "Error in IdexLevelCalibration.idexConfigStep2: {}".format(e), overlay=True)
            try:
                self.movie1.stop()
                self.movie2.stop()
            except:
                pass

    def idexConfigStep3(self):
        """
        levels second leveling position (LEFT)
        """
        logger.info("IdexLevelCalibration.idexConfigStep3 started")
        try:
            self.stackedWidget.setCurrentWidget(self.idexConfigStep3Page)
            self.octoprint_client.jog(z=10, absolute=True, speed=1500)
            self.octoprint_client.jog(
                x=self.main_window.printer_model.calibrationPosition['X2'],
                y=self.main_window.printer_model.calibrationPosition['Y2'],
                absolute=True, speed=10000
            )
            self.octoprint_client.jog(z=0, absolute=True, speed=1500)
            self.movie2.stop()
            self.movie3 = QtGui.QMovie(
                os.path.join(os.path.dirname(__file__), "resources", "CalibrationPoint2.gif")
            )
            self.movie3.setCacheMode(QtGui.QMovie.CacheNone)  # Avoid loading entire GIF into memory
            self.CalibrationPoint2.setMovie(self.movie3)
            self.movie3.start()
        except Exception as e:
            logger.error("Error in IdexLevelCalibration.idexConfigStep3: {}".format(e))
            dialog.WarningOk(self, "Error in IdexLevelCalibration.idexConfigStep3: {}".format(e), overlay=True)
            try:
                self.movie2.stop()
                self.movie3.stop()
            except:
                pass

    def idexConfigStep4(self):
        """
        Set to Mirror mode and asks to loosen the carriage, push both doen to max
        :return:
        """
        logger.info("IdexLevelCalibration.idexConfigStep4 started")
        try:
            self.stackedWidget.setCurrentWidget(self.idexConfigStep4Page)
            self.octoprint_client.jog(z=10, absolute=True, speed=1500)
            self.octoprint_client.gcode(command='M605 S3')
            self.octoprint_client.jog(
                x=self.main_window.printer_model.calibrationPosition['X1'],
                y=self.main_window.printer_model.calibrationPosition['Y1'],
                absolute=True, speed=10000
            )
            self.movie3.stop()
            gif_path = os.path.join(os.path.dirname(__file__), "resources", "NozzleLevelNew1.gif")
            if not os.path.exists(gif_path):
                self.logger.error(f"IDEX Calibration GIF missing: {gif_path}")
            else:
                self.movie4 = QtGui.QMovie(gif_path)
                self.movie4.setCacheMode(QtGui.QMovie.CacheNone)  # Avoid loading entire GIF into memory
                self.CalibrationPoint3.setMovie(self.movie4)
                self.movie4.start()
        except Exception as e:
            logger.error("Error in IdexLevelCalibration.idexConfigStep4: {}".format(e))
            dialog.WarningOk(self, "Error in IdexLevelCalibration.idexConfigStep4: {}".format(e), overlay=True)
            try:
                self.movie3.stop()
                self.movie4.stop()
            except:
                pass

    def idexConfigStep5(self):
        """
        take bed up until both nozzles touch the bed. ASk to take nozzle up and down till nozzle just rests on the bed and tighten
        :return:
        """
        logger.info("IdexLevelCalibration.idexConfigStep5 started")
        try:
            self.stackedWidget.setCurrentWidget(self.idexConfigStep5Page)
            self.octoprint_client.jog(z=1, absolute=True, speed=10000)
            self.movie4.stop()
            gif_path = os.path.join(os.path.dirname(__file__), "resources", "NozzlelevelNew2.gif")
            if not os.path.exists(gif_path):
                self.logger.error(f"IDEX Calibration GIF missing: {gif_path}")
            else:
                self.movie5 = QtGui.QMovie(gif_path)
                self.movie5.setCacheMode(QtGui.QMovie.CacheNone)  # Avoid loading entire GIF into memory
                self.NozzleLevel2.setMovie(self.movie5)
                self.movie5.start()
        except Exception as e:
            logger.error("Error in IdexLevelCalibration.idexConfigStep5: {}".format(e))
            dialog.WarningOk(self, "Error in IdexLevelCalibration.idexConfigStep5: {}".format(e), overlay=True)
            try:
                self.movie4.stop()
                self.movie5.stop()
            except:
                pass

    def idexDoneStep(self):
        """
        Exits leveling
        :return:
        """
        logger.info("IdexLevelCalibration.idexDoneStep started")
        try:
            self.octoprint_client.jog(z=4, absolute=True, speed=1500)
            self.main_window.calibrate_screen.show_calibrate_screen()
            self.movie5.stop()
            self.octoprint_client.home(['z'])
            self.octoprint_client.home(['x', 'y'])
            self.octoprint_client.gcode(command='M104 S0')
            self.octoprint_client.gcode(command='M104 T1 S0')
            self.octoprint_client.gcode(command='M605 S1')
            self.octoprint_client.gcode(command='M218 T1 Z0') #set nozzle offsets to 0
            self.octoprint_client.gcode(command='M84')
            self.octoprint_client.gcode(command='M500')  # store eeprom settings to get Z home offset, mesh bed leveling back
        except Exception as e:
            logger.error("Error in IdexLevelCalibration.idexDoneStep: {}".format(e))
            dialog.WarningOk(self, "Error in IdexLevelCalibration.idexDoneStep: {}".format(e), overlay=True)
            try:
                self.movie5.stop()
            except:
                pass

    def idexCancelStep(self):
        logger.info("IdexLevelCalibration.idexCancelStep started")
        try:
            self.main_window.calibrate_screen.show_calibrate_screen()
            try:
                self.movie1.stop()
                self.movie2.stop()
                self.movie3.stop()
                self.movie4.stop()
                self.movie5.stop()
            except:
                pass
            self.octoprint_client.gcode(command='M605 S1')
            self.octoprint_client.home(['z'])
            self.octoprint_client.home(['x', 'y'])
            self.octoprint_client.gcode(command='M104 S0')
            self.octoprint_client.gcode(command='M104 T1 S0')
            # Fix incorrect attribute access to printer_model
            self.octoprint_client.gcode(
                command='M218 T1 Z{}'.format(self.main_window.printer_model.tool_offsets['Z'])
            )
            self.octoprint_client.gcode(command='M84')
        except Exception as e:
            logger.error("Error in IdexLevelCalibration.idexCancelStep: {}".format(e))
            dialog.WarningOk(self, "Error in IdexLevelCalibration.idexCancelStep: {}".format(e), overlay=True)
