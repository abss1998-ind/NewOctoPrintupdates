import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QLabel, QProgressBar
from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtGui import QMovie
from utils.helpers import check_ui_elements
from utils.logger import get_logger
# Add resource import
import ui.resources.resource_rc

class LoadingScreen(QWidget):
    def __init__(self, main_window):
        super(LoadingScreen, self).__init__()
        self.logger = get_logger(self.__class__.__name__)
        self.main_window = main_window
        
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "loading_screen.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("LoadingScreen UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load LoadingScreen UI file: {e}")

        """ ---------- Initialize UI components ---------- """
        
        # Find and initialize UI components from the loading_screen.ui
        self.loading = self.findChild(QLabel, "loading")
        self.loadingProgressBar = self.findChild(QProgressBar, "loadingProgressBar")

        
        # Validate that all components were found
        all_components = [
            self.loading,
            self.loadingProgressBar
        ]
        
        # Use the helper function to check and report missing widgets
        check_ui_elements(self, all_components, "LoadingScreen")
        
        # Initialize component states
        self.loadingProgressBar.setValue(0)
        self.loadingProgressBar.setMinimum(0)
        self.loadingProgressBar.setMaximum(100)
        
        self.loading.setText("Initializing...")
        
        self.logger.info("LoadingScreen components initialized successfully")

    def update_progress(self, value, message="Loading..."):
        """Update the progress bar and loading message"""
        self.loadingProgressBar.setValue(value)
        self.loading.setText(message)
        # Force GUI update
        self.repaint()
        self.logger.info(f"Progress updated: {value}% - {message}")