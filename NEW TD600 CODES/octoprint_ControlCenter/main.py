import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from ui.main_window import MainWindow
from controller.main_controller import MainController
from utils.logger import get_logger

def main():
    logger = get_logger(__name__)
    logger.info(f"Starting Control Center application")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Running on: {os.name} platform")
    try:
        app = QApplication(sys.argv)
        logger.info("QApplication initialized")
        controller = MainController()
        controller.start()
        logger.info("Main window displayed")
        exit_code = app.exec_()
        logger.info(f"Application exiting with code {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        logger.exception("Failed to start application")
        raise

if __name__ == "__main__":
    main()