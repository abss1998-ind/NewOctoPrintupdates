"""
Z Probe Offset Calibration Wizard
=================================

Manual probe offset calibration wizard for IDEX printers using bed movement and position measurement.

Architecture:
- MVP pattern with model signals for position communication
- 4-step wizard: Welcome → Probe → Manual Calibration → Results
- Timeout handling for robust probe operation failure recovery
- Manual bed movement with 0.05mm increments

Workflow:
1. Welcome - Introduction and preparation (homing, heating tool 0)
2. Probe - Automated probe accuracy check to get reference position
3. Manual - Manual bed movement with video guidance at probe position + 1mm
4. Results - Calculate difference and apply Z offset using M851

Features:
- Tool 0 only heating and calibration
- Automatic probe sequencing with quality assessment
- Manual bed movement in 0.05mm increments
- Video guidance with GIF playback
- Timeout handling with retry/cancel options
- Proper Z offset calculation and application via M851
- Comprehensive error handling and user feedback

Dependencies:
- OctoPrint client for G-code commands
- Printer model for probe result signals and current position retrieval
- PyQt5 UI framework with QMovie for GIF display
- Custom dialog utilities for user interaction
"""

import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QLabel
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QMovie
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import dialog
import time


class ZProbeOffsetWizard(QWidget):
    """
    Z Probe Offset Calibration Wizard
    ===============================
    
    Manual probe offset calibration wizard for Z probe offset calibration using bed movement.
    
    This wizard provides a streamlined 4-step process:
    1. Welcome - Introduction, preparation, tool 0 heating, and axis homing
    2. Probe - Automated probe accuracy check to establish reference position
    3. Manual - Manual bed movement with video guidance for precise calibration
    4. Results - Calculate offset difference and apply via M851
    
    Key Features:
    - Tool 0 only heating and calibration (no tool switching)
    - Automatic probe sequencing with quality assessment
    - Manual bed movement in 0.05mm increments with video guidance
    - Timeout handling for probe operation failures
    - Proper Z offset calculation using difference between probe and manual positions
    - M851 application for probe offset setting
    - Comprehensive error handling with user-friendly feedback
    
    Architecture:
    - Uses MVP pattern with model signals for probe result and position communication
    - Timeout-based error recovery for robust operation
    - Video guidance using QMovie for GIF playback
    - Proper state management and cleanup on wizard exit
    
    Probe Quality Assessment:
    - Excellent: std_dev < 0.01mm
    - Good: std_dev < 0.02mm  
    - Acceptable: std_dev < 0.05mm
    - Poor: std_dev >= 0.05mm
    """

    # ==================== CONSTANTS AND CONFIGURATION ====================
    
    # Step indices for clarity and maintainability
    STEP_WELCOME = 0
    STEP_PROBE = 1
    STEP_MANUAL = 2
    STEP_RESULTS = 3
    TOTAL_STEPS = 4
    
    # Timeout configuration
    PROBE_TIMEOUT_SECONDS = 30  # Timeout for probe operations
    POSITION_TIMEOUT_SECONDS = 5  # Timeout for M114 position recording
    
    # Quality thresholds for probe standard deviation (mm)
    QUALITY_EXCELLENT = 0.01
    QUALITY_GOOD = 0.02
    QUALITY_ACCEPTABLE = 0.05
    
    # Movement configuration
    MOVEMENT_INCREMENT = 0.05  # Z movement increment in mm
    NOZZLE_HEATING_TEMP = 180  # Tool 0 heating temperature

    # ==================== INITIALIZATION AND SETUP ====================

    def __init__(self, main_window):
        """
        Initialize the Z Probe Offset Wizard.
        
        Sets up UI components, state variables, and signal connections for the manual
        Z probe offset calibration process.
        
        Args:
            main_window: Main application window providing access to printer model and OctoPrint client
        """
        super().__init__()
        self.main_window = main_window
        self.model = main_window.printer_model
        self.octoprint_client = main_window.octoprint_client
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing Z Probe Offset Wizard")

        # Initialize state variables
        self._init_state_variables()
        
        # Load UI and initialize components
        self._load_ui()
        self._init_ui_components()
        self._connect_signals()

        self.logger.info("Z Probe Offset Wizard initialized successfully")

    def _init_state_variables(self):
        """
        Initialize all state tracking variables.
        
        Sets up probe result storage, position tracking, signal connection tracking,
        wizard navigation state, and timeout handling variables.
        """
        # Probe and position data storage
        self.probe_result = None           # Will store probe accuracy result
        self.manual_position = None        # Will store manual M114 position
        self.probe_average_z = None        # Average Z from probe accuracy
        self.manual_z = None               # Manual Z position from M114
        self.calculated_offset = None      # Calculated probe offset ready for application

        # Signal connection tracking
        self._probe_tracking_connected = False
        self._position_tracking_connected = False

        # Wizard navigation state
        self._current_step = 0
        self.calibration_complete = False
        
        # Timeout handling
        self.probe_timeout_timer = None         # QTimer for probe operation timeouts
        self.position_timeout_timer = None      # QTimer for position recording timeouts
        
        # Video playback
        self.current_movie = None               # Current QMovie instance

    def _load_ui(self):
        """
        Load the UI file with proper error handling.
        
        Raises:
            Exception: If UI file cannot be loaded
        """
        try:
            ui_file_path = os.path.join(os.path.dirname(__file__), "ZProbeOffsetWizard.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("ZProbeOffsetWizard UI loaded successfully")
        except Exception as e:
            self.logger.exception(f"Failed to load ZProbeOffsetWizard UI file: {e}")
            raise

    def _init_ui_components(self):
        """
        Initialize and validate all UI components.
        
        Finds all required UI elements and validates their existence for robust operation.
        """
        # Main navigation components
        self.stackedWidget = self.findChild(QStackedWidget, "stackedWidget")
        self.welcomePage = self.findChild(QWidget, "welcomePage")
        self.automaticProbingStep = self.findChild(QWidget, "automaticProbingStep")
        self.calibrationPage = self.findChild(QWidget, "calibrationPage")
        self.resultsPage = self.findChild(QWidget, "resultsPage")
        
        # Labels for user feedback
        self.stepLabel = self.findChild(QLabel, "stepLabel")
        self.calibrationLabel = self.findChild(QLabel, "calibrationLabel")
        self.automaticProbingStepLabel = self.findChild(QLabel, "automaticProbingStepLabel")
        self.bedUpDownLabel = self.findChild(QLabel, "bedUpDownLabel")
        self.restulsLabel = self.findChild(QLabel, "restulsLabel")
        self.step1Gif = self.findChild(QLabel, "step1Gif")

        # Navigation buttons
        self.nextButton = self.findChild(QPushButton, "nextButton")
        self.cancelButton = self.findChild(QPushButton, "cancelButton")

        # Manual movement buttons
        self.bedUpButton = self.findChild(QPushButton, "bedUpButton")
        self.bedDownButton = self.findChild(QPushButton, "bedDownButton")

        # Validate all required UI components exist
        required_components = [
            self.stackedWidget, self.welcomePage, self.automaticProbingStep, 
            self.calibrationPage, self.resultsPage, self.nextButton, 
            self.cancelButton, self.stepLabel
        ]
        check_ui_elements(self, required_components, "ZProbeOffsetWizard")

    def _connect_signals(self):
        """
        Connect all signal handlers.
        
        Sets up button connections and prepares for model signal connections.
        Note: probe_accuracy_result_received and current_position_updated signals 
        are connected only when needed during respective operations.
        """
        # Navigation button connections
        if self.nextButton:
            self.nextButton.clicked.connect(self.on_next_clicked)
        if self.cancelButton:
            self.cancelButton.clicked.connect(self.on_cancel_clicked)

        # Manual movement button connections
        if self.bedUpButton:
            self.bedUpButton.clicked.connect(self.on_bed_up_clicked)
        if self.bedDownButton:
            self.bedDownButton.clicked.connect(self.on_bed_down_clicked)

    # ==================== WIZARD LIFECYCLE AND NAVIGATION ====================

    def showEvent(self, event):
        """
        Handle wizard activation - reset state and prepare printer.
        
        Called when the wizard widget becomes visible. Performs complete state
        reset including signal disconnections and data cleanup, then resets wizard
        to welcome step, heats tool 0, and homes the printer for consistent starting position.
        
        Args:
            event: Qt show event
        """
        super().showEvent(event)
        try:
            # Complete state reset including signal disconnections
            self._reset_wizard_state()
            
            self.logger.info("🔄✨ Z Probe Offset calibration started - complete state reset, heating tool 0 and homing")
            
            # Validate we have necessary components
            if not self.octoprint_client:
                self.logger.error("No OctoPrint client available")
                self._show_error("Connection Error", "No OctoPrint client available. Please check connection.")
                return
                
            if not self.model:
                self.logger.error("No printer model available")
                self._show_error("Model Error", "No printer model available. Please restart the application.")
                return
            
            # Get latest configuration from printer (similar to camera wizard)
            self.logger.info("Getting latest probe offset configuration")
            self.octoprint_client.gcode(command='M503')
            
            # Heat tool 0 only (no tool switching needed)
            self.octoprint_client.gcode(f"M104 T0 S{self.NOZZLE_HEATING_TEMP}")
            
            # Home all axes for consistent starting position
            self.octoprint_client.home(['x', 'y', 'z'])
            self.octoprint_client.jog(x=0, y=0, z=5, absolute=True, speed=9000)  # Raise Z slightly
            
        except Exception as e:
            self.logger.error(f"Error in ZProbeOffsetWizard showEvent: {e}")
            self._show_error("Initialization Error", str(e))

    def goto_step(self, index: int):
        """
        Navigate to the specified wizard step with proper setup.
        
        Handles step bounds checking, UI page switching, and step-specific initialization.
        Each step has its own setup method for clean separation of concerns.
        
        Args:
            index (int): Step index to navigate to (0-based, will be bounds-checked)
        """
        index = max(0, min(index, self.TOTAL_STEPS - 1))
        prev_step = getattr(self, "_current_step", 0)

        self._current_step = index
        
        # Update UI to show correct page
        if self.stackedWidget:
            if index == self.STEP_WELCOME:
                self.stackedWidget.setCurrentWidget(self.welcomePage)
            elif index == self.STEP_PROBE:
                self.stackedWidget.setCurrentWidget(self.automaticProbingStep)
            elif index == self.STEP_MANUAL:
                self.stackedWidget.setCurrentWidget(self.calibrationPage)
            elif index == self.STEP_RESULTS:
                self.stackedWidget.setCurrentWidget(self.resultsPage)
        
        # Update step indicator
        self._update_step_label()

        # Execute step-specific setup
        if index == self.STEP_WELCOME:
            self._setup_welcome_step()
        elif index == self.STEP_PROBE:
            self._setup_probe_step()
        elif index == self.STEP_MANUAL:
            self._setup_manual_step()
        elif index == self.STEP_RESULTS:
            self._setup_results_step()

        self.logger.info(f"Switched to step {index + 1}/{self.TOTAL_STEPS}")

    def _update_step_label(self):
        """
        Update the step progress indicator.
        
        Shows current step number and total steps for user orientation.
        """
        if not self.stepLabel:
            return
        
        try:
            self.stepLabel.setText(f"Step {self._current_step + 1}/{self.TOTAL_STEPS}")
        except Exception as e:
            self.logger.error(f"Error updating step label: {e}")

    # ==================== STEP SETUP AND CONFIGURATION ====================

    def _setup_welcome_step(self):
        """
        Configure UI for the welcome step.
        
        Sets up the initial welcome interface with appropriate button text and content.
        """
        try:
            if self.nextButton:
                self.nextButton.setText("Start Calibration")
                self.nextButton.setEnabled(True)
                
            if self.calibrationLabel:
                self.calibrationLabel.setText(
                    "Z Probe Offset Calibration\n\n"
                    "This wizard will help you calibrate the Z probe offset for accurate first layer printing.\n\n"
                    "The process involves:\n"
                    "• Heating tool 0 and homing the printer\n"
                    "• Running probe accuracy test for reference\n"
                    "• Manual bed adjustment using paper as feeler gauge\n"
                    "Wait for moves to finish before clicking Next."
                )
        except Exception as e:
            self.logger.error(f"Error setting up welcome step: {e}")

    def _setup_probe_step(self):
        """
        Configure UI and start the automated probe accuracy test.
        
        Connects probe tracking, updates UI to processing state, and initiates the
        probe accuracy sequence after a short delay to ensure signal connections are ready.
        """
        try:
            self.logger.info("Setting up probe step")
            
            # Reset probe state in case of retry
            self.probe_result = None
            self.probe_average_z = None
            
            # Stop any existing timeout timer
            if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
                self.probe_timeout_timer.stop()
                self.probe_timeout_timer = None
                self.logger.debug("Cleaned up existing probe timeout timer")
            
            # Disconnect any existing probe tracking before connecting new one
            self._disconnect_probe_tracking()
            
            # Connect probe tracking FIRST before starting any probe operations
            self._connect_probe_tracking()
            
            # Update button to processing state
            if self.nextButton:
                self.nextButton.setText("Processing...")
                self.nextButton.setEnabled(False)
            
            # Show initial status
            if self.automaticProbingStepLabel:
                self.automaticProbingStepLabel.setText(
                    "🔧 Running Probe Accuracy Test...\n\n"
                    "• Moving to bed center\n"
                    "• Running probe accuracy sequence\n"
                    "• Measuring average probe position\n"
                    "• This will serve as our reference point\n\n"
                    "Status: Initializing probe test..."
                )
            
            self.logger.info("Starting probe accuracy sequence")
            # Use QTimer to ensure signal connection is complete before starting probe sequence
            QTimer.singleShot(100, self.start_probe_sequence)
            
        except Exception as e:
            self.logger.error(f"Error setting up probe step: {e}")
            self._show_error("Error starting probe test", str(e))

    def _setup_manual_step(self):
        """
        Configure UI for the manual calibration step.
        
        Starts video playback, enables movement buttons, and positions nozzle 1mm above probe point.
        """
        try:
            # Start video playback
            self._play_calibration_video()
            
            # Update button state
            if self.nextButton:
                self.nextButton.setText("Record Position")
                self.nextButton.setEnabled(True)
                
            # Enable movement buttons
            if self.bedUpButton:
                self.bedUpButton.setEnabled(True)
            if self.bedDownButton:
                self.bedDownButton.setEnabled(True)
            
            # Move to 1mm above the probe position
            if self.probe_average_z is not None:
                target_z = self.probe_average_z + 1.0  # 1mm above probe position
                self.octoprint_client.jog(z=target_z, absolute=True, speed=300)
                
                if self.bedUpDownLabel:
                    self.bedUpDownLabel.setText(
                        f'Use the "Up" and "Down" buttons to move the bed in 0.05mm increments.\n\n'
                        f'Use paper as a feeler gauge between nozzle and bed.\n\n'
                        f'Current position: {target_z:.3f}mm (1mm above probe point)\n'
                        f'Probe reference: {self.probe_average_z:.6f}mm\n\n'
                        f'When properly calibrated, click "Record Position"'
                    )
                
                self.logger.info(f"Moved to manual calibration position: {target_z:.3f}mm")
            else:
                self.logger.error("No probe average Z available for manual step")
                self._show_error("Error", "No probe reference position available. Please restart calibration.")
                
        except Exception as e:
            self.logger.error(f"Error setting up manual step: {e}")
            self._show_error("Error setting up manual calibration", str(e))

    def _setup_results_step(self):
        """
        Configure UI for the results step.
        
        Shows calculation results and prepares for offset application.
        """
        try:
            if self.nextButton:
                self.nextButton.setText("Apply Offset")
                self.nextButton.setEnabled(True)
                
            # Stop any video playback
            self._stop_current_video()
            
        except Exception as e:
            self.logger.error(f"Error setting up results step: {e}")

    # ==================== USER INTERACTION HANDLERS ====================

    def on_next_clicked(self):
        """
        Handle next button clicks with step-based navigation and validation.
        
        Provides different behavior based on current wizard step:
        - Welcome: Validate components and advance to probe step
        - Probe: Advance to manual step (only if probe data is collected)
        - Manual: Record current position and advance to results
        - Results: Apply offset and finish calibration
        """
        self.logger.info("Next button clicked")
        try:
            if self._current_step == self.STEP_WELCOME:
                # Validate essential components before proceeding
                if not self.octoprint_client:
                    dialog.WarningOk(self, "No OctoPrint connection available. Please check connection.", overlay=True)
                    return
                if not self.model:
                    dialog.WarningOk(self, "No printer model available. Please restart the application.", overlay=True)
                    return
                # Move to probe step
                self.goto_step(self.STEP_PROBE)
            elif self._current_step == self.STEP_PROBE:
                # Only allow advancing if probe data is collected
                if self.probe_result is not None and self.probe_average_z is not None:
                    self.goto_step(self.STEP_MANUAL)
                else:
                    dialog.WarningOk(self, "Please wait for probe test to complete.", overlay=True)
            elif self._current_step == self.STEP_MANUAL:
                # Validate we don't already have position data (prevent duplicates)
                if self.manual_position is not None:
                    dialog.WarningOk(self, "Position already recorded. Please proceed to next step.", overlay=True)
                    return
                # Record current position and move to results
                self.record_manual_position()
            elif self._current_step == self.STEP_RESULTS:
                # Apply offset and finish
                if self.calibration_complete:
                    self.apply_and_finish()
                else:
                    dialog.WarningOk(self, "Calibration not complete. Please restart.", overlay=True)
                    
        except Exception as e:
            self.logger.error(f"Error in on_next_clicked: {e}")
            self._show_error("Navigation Error", str(e))

    def on_cancel_clicked(self):
        """
        Handle cancel button - reset wizard and return to main screen.
        
        Performs complete cleanup including wizard state reset, printer homing,
        and navigation back to the main calibration screen.
        """
        self.logger.info("Cancel button clicked")
        try:
            # Cleanup only - do NOT restart wizard when canceling
            self.cleanup()
            
            # Turn off heating and home
            if self.octoprint_client:
                self.octoprint_client.gcode("M104 T0 S0")  # Turn off tool 0 heater
                self.octoprint_client.home(['x', 'y', 'z'])
            
            # Return to main calibration screen
            if hasattr(self.main_window, 'calibrate_screen'):
                self.main_window.calibrate_screen.show_calibrate_screen()
            
        except Exception as e:
            self.logger.error(f"Error in on_cancel_clicked: {e}")
            # Still try to return to main screen even if there's an error
            if hasattr(self.main_window, 'calibrate_screen'):
                self.main_window.calibrate_screen.show_calibrate_screen()

    def on_bed_up_clicked(self):
        """
        Handle bed up button - move bed up by increment.
        
        Moves the bed up (nozzle relatively down) by the configured increment.
        Only works during the manual calibration step.
        """
        try:
            # Only allow movement during manual step
            if self._current_step != self.STEP_MANUAL:
                self.logger.warning("Bed movement only allowed during manual calibration step")
                return
                
            if not self.octoprint_client:
                dialog.WarningOk(self, "No OctoPrint connection available.", overlay=True)
                return
                
            self.logger.info(f"Moving bed up by {self.MOVEMENT_INCREMENT}mm")
            self.octoprint_client.jog(z=-self.MOVEMENT_INCREMENT, speed=300)
        except Exception as e:
            self.logger.error(f"Error moving bed up: {e}")

    def on_bed_down_clicked(self):
        """
        Handle bed down button - move bed down by increment.
        
        Moves the bed down (nozzle relatively up) by the configured increment.
        Only works during the manual calibration step.
        """
        try:
            # Only allow movement during manual step
            if self._current_step != self.STEP_MANUAL:
                self.logger.warning("Bed movement only allowed during manual calibration step")
                return
                
            if not self.octoprint_client:
                dialog.WarningOk(self, "No OctoPrint connection available.", overlay=True)
                return
                
            self.logger.info(f"Moving bed down by {self.MOVEMENT_INCREMENT}mm")
            self.octoprint_client.jog(z=self.MOVEMENT_INCREMENT, speed=300)
        except Exception as e:
            self.logger.error(f"Error moving bed down: {e}")

    # ==================== AUTOMATED PROBE SEQUENCE ====================

    def start_probe_sequence(self):
        """
        Initialize and start the probe accuracy sequence.
        
        Moves to bed center and initiates probe accuracy test for reference measurement.
        """
        try:
            self.logger.info("Starting probe accuracy sequence")
            
            # Calculate bed center position
            build_size = getattr(self.model, 'machineBuildSize', {'X': 300, 'Y': 300}) if self.model else {'X': 300, 'Y': 300}
            center_x = int(build_size.get('X', 300) / 2)  # Center of bed X
            center_y = int(build_size.get('Y', 300) / 2)  # Center of bed Y
            
            self.logger.info(f"Using bed size: {build_size.get('X')}x{build_size.get('Y')}mm, probing at center X{center_x} Y{center_y}")
            
            # Update status
            if self.automaticProbingStepLabel:
                self.automaticProbingStepLabel.setText(
                    "🔧 Running Probe Accuracy Test...\n\n"
                    "• Moving to bed center\n"
                    "• Positioning for probe test\n"
                    "• Running probe sequence\n\n"
                    "Status: Moving to probe position..."
                )
            
            # Move to center position
            self.octoprint_client.jog(x=center_x, y=center_y, z=5, absolute=True, speed=8000)

            # Start probing after movement delay
            QTimer.singleShot(2000, self._start_probe_accuracy)
            
        except Exception as e:
            self.logger.error(f"Error starting probe sequence: {e}")
            self._show_error("Probe Sequence Error", str(e))

    def _start_probe_accuracy(self):
        """
        Start the probe accuracy test with timeout handling.
        
        Initiates the PROBE_ACCURACY command and sets up timeout monitoring.
        """
        try:
            self.logger.info("Starting probe accuracy test")
            
            # Update status
            if self.automaticProbingStepLabel:
                self.automaticProbingStepLabel.setText(
                    "🔧 Running Probe Accuracy Test...\n\n"
                    "• Probe positioned at bed center\n"
                    "• Running accuracy test sequence\n"
                    "• Measuring reference position\n\n"
                    "Status: Probing... Please wait."
                )
            
            # Set up timeout for probe result
            if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
                self.probe_timeout_timer.stop()
                self.logger.debug("Stopped existing probe timeout timer")
            
            self.probe_timeout_timer = QTimer()
            self.probe_timeout_timer.setSingleShot(True)
            self.probe_timeout_timer.timeout.connect(self._handle_probe_timeout)
            self.probe_timeout_timer.start(self.PROBE_TIMEOUT_SECONDS * 1000)  # Convert to milliseconds
            self.logger.info(f"Started probe timeout timer for {self.PROBE_TIMEOUT_SECONDS} seconds")
            
            # Run probe accuracy macro
            self.logger.info("Running PROBE_ACCURACY PROBE_SPEED=3")
            self.octoprint_client.gcode(command='PROBE_ACCURACY PROBE_SPEED=3')
            
        except Exception as e:
            self.logger.error(f"Error starting probe accuracy: {e}")
            self._show_error("Error starting probe test", str(e))

    # ==================== PROBE RESULT PROCESSING ====================

    def on_probe_result_received(self, tool_name, probe_data):
        """
        Handle probe result signals from the printer model.
        
        Simplified approach: Process probe results only if we don't already have them.
        
        Args:
            tool_name (str): Tool identifier (should be "tool0" for this wizard)
            probe_data (dict): Complete probe data with average, std_dev, etc.
        """
        try:
            self.logger.info(f"Received probe result signal: {tool_name} = {probe_data}")
            
            # Check if we already have probe results (prevent duplicate processing)
            if self.probe_result is not None:
                self.logger.debug("Ignoring probe result - already have results")
                return
            
            # Cancel timeout timer since we got a probe result
            if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
                self.probe_timeout_timer.stop()
                self.probe_timeout_timer = None
                self.logger.debug("Probe timeout timer stopped successfully")
            
            # Store the probe data
            self.probe_result = probe_data
            self.probe_average_z = probe_data.get('average', 0.0)
            std_dev = probe_data.get('standard_deviation', 0.0)
            
            # Determine quality based on standard deviation
            quality = self._assess_probe_quality(std_dev)
            
            self.logger.info(f"Probe complete - Average Z: {self.probe_average_z:.6f}mm, Quality: {quality}")
            
            # Update UI with completion status
            if self.automaticProbingStepLabel:
                self.automaticProbingStepLabel.setText(
                    f"✅ Probe Test Complete!\n\n"
                    f"• Reference Position: {self.probe_average_z:.6f}mm\n"
                    f"• Standard Deviation: {std_dev:.6f}mm\n"
                    f"• Quality: {quality}\n\n"
                    f"The probe has established a reference position.\n\n"
                    f"Click 'Next' to proceed to manual calibration."
                )
            
            # Enable next button
            if self.nextButton:
                self.nextButton.setText("Next")
                self.nextButton.setEnabled(True)
            
            # Disconnect probe tracking since we got the result we needed
            self._disconnect_probe_tracking()
                
        except Exception as e:
            self.logger.error(f"Error in on_probe_result_received: {e}")
            self._disconnect_probe_tracking()
            self._show_error("Error processing probe result", str(e))

    # ==================== MANUAL POSITION RECORDING ====================

    def record_manual_position(self):
        """
        Record the current manual position using M114.
        
        Connects position tracking, sends M114 command, and waits for position response.
        """
        try:
            self.logger.info("Recording manual position")
            
            # Disconnect any existing position tracking before connecting new one
            self._disconnect_position_tracking()
            
            # Connect position tracking
            self._connect_position_tracking()
            
            # Update button state
            if self.nextButton:
                self.nextButton.setText("Recording...")
                self.nextButton.setEnabled(False)
            
            # Set up timeout for position recording
            if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
                self.position_timeout_timer.stop()
            
            self.position_timeout_timer = QTimer()
            self.position_timeout_timer.setSingleShot(True)
            self.position_timeout_timer.timeout.connect(self._handle_position_timeout)
            self.position_timeout_timer.start(self.POSITION_TIMEOUT_SECONDS * 1000)
            
            # Send M114 to get current position
            self.logger.info("Sending M114 to record current position")
            self.octoprint_client.gcode("M114")
            
        except Exception as e:
            self.logger.error(f"Error recording manual position: {e}")
            self._show_error("Error recording position", str(e))

    def on_position_updated(self, position_data):
        """
        Handle position update from M114 response.
        
        Simplified approach: Only process if we're in manual step and don't have position yet.
        
        Args:
            position_data (dict): Position data with 'x', 'y', 'z' keys
        """
        try:
            # Only process position updates during manual step and if we don't have position yet
            if self._current_step != self.STEP_MANUAL or self.manual_position is not None:
                self.logger.debug("Ignoring position update - not in manual step or already have position")
                return
                
            self.logger.info(f"Received position update: {position_data}")
            
            # Cancel timeout timer
            if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
                self.position_timeout_timer.stop()
                self.position_timeout_timer = None
                self.logger.debug("Position timeout timer stopped successfully")
            
            # Store position data
            self.manual_position = position_data
            self.manual_z = position_data.get('z', 0.0)
            
            self.logger.info(f"Manual position recorded - Z: {self.manual_z:.6f}mm")
            
            # Disconnect position tracking
            self._disconnect_position_tracking()
            
            # Calculate offset and move to results
            self.calculate_probe_offset()
            
        except Exception as e:
            self.logger.error(f"Error in on_position_updated: {e}")
            self._disconnect_position_tracking()
            self._show_error("Error processing position", str(e))

    # ==================== OFFSET CALCULATION AND APPLICATION ====================

    def calculate_probe_offset(self):
        """
        Calculate the probe offset based on probe and manual positions.
        
        The probe offset is the difference between the probed position and manual position.
        """
        try:
            if self.probe_average_z is None or self.manual_z is None:
                self.logger.error("Missing probe or manual position data")
                self._show_error("Error", "Missing position data. Please restart calibration.")
                return
            
            # Calculate the offset difference
            # Offset = manual position - probe position
            # This represents how much higher/lower the manual position is compared to probe
            offset_difference =  self.probe_average_z - self.manual_z 
            
            # Store calculated offset for use in apply_and_finish
            self.calculated_offset = offset_difference 
            
            self.logger.info(f"Probe position: {self.probe_average_z:.6f}mm")
            self.logger.info(f"Manual position: {self.manual_z:.6f}mm")
            self.logger.info(f"Calculated offset difference: {offset_difference:.6f}mm")
            
            # Mark calibration as complete
            self.calibration_complete = True
            
            # Move to results step and show calculation
            self.goto_step(self.STEP_RESULTS)
            
            # Update results display
            if self.restulsLabel:
                self.restulsLabel.setText(
                    f"🎯 CALIBRATION COMPLETE!\n\n"
                    f"📊 MEASUREMENT RESULTS:\n"
                    f"Probe Reference: {self.probe_average_z:.6f}mm\n"
                    f"Manual Position: {self.manual_z:.6f}mm\n\n"
                    f"🔧 PROBE OFFSET CALCULATION:\n"
                    f"Offset Difference: {offset_difference:.6f}mm\n\n"
                    f"✅ Ready to apply the new probe offset.\n"
                    f"Click 'Apply Offset' to save and complete calibration."
                )
            
            self.logger.info("Probe offset calculation complete")
            
        except Exception as e:
            self.logger.error(f"Error calculating probe offset: {e}")
            self._show_error("Calculation Error", str(e))

    def apply_and_finish(self):
        """
        Apply the calculated probe offset and finish calibration.
        
        Applies M851 command with calculated offset and returns to main screen.
        """
        try:
            if not hasattr(self, 'calculated_offset') or self.calculated_offset is None:
                self.logger.error("Cannot apply offset - no calculated offset available")
                self._show_error("Error", "No calculated offset available. Please complete the calibration process first.")
                return
            
            self.logger.info(f"Applying previously calculated probe offset: {self.calculated_offset:.6f}mm")
            
            # Update status
            if self.restulsLabel:
                self.restulsLabel.setText(
                    "🔧 APPLYING PROBE OFFSET...\n\n"
                    "• Saving offset to printer configuration\n"
                    "• Using M851 command\n"
                    "• Writing to EEPROM\n\n"
                    "Please wait..."
                )
            
            # Disable button during application
            if self.nextButton:
                self.nextButton.setEnabled(False)
                self.nextButton.setText("Applying...")
            
            # Apply the probe offset using M851
            offset_command = f"M851 Z{self.calculated_offset:.6f}"
            self.logger.info(f"Setting probe offset with command: {offset_command}")
            self.octoprint_client.gcode(command=offset_command)
            
            # Save to EEPROM
            self.octoprint_client.gcode(command='M500')
            
            self.logger.info(f"Probe offset {self.calculated_offset:.6f}mm applied and saved")
            
            # Clean up and return to main screen (cleanup only, no restart)
            self.cleanup()
            
            # Turn off heating and home
            self.octoprint_client.gcode("M104 T0 S0")  # Turn off tool 0 heater
            self.octoprint_client.home(['x', 'y', 'z'])
            self.octoprint_client.gcode("RESTART")

            # Return to main calibration screen
            if hasattr(self.main_window, 'calibrate_screen'):
                self.main_window.calibrate_screen.show_calibrate_screen()
            
        except Exception as e:
            self.logger.error(f"Error applying probe offset: {e}")
            self._show_error("Application Error", str(e))

    # ==================== TIMEOUT AND ERROR HANDLING ====================

    def _handle_probe_timeout(self):
        """
        Handle probe result timeout with user interaction.
        
        Simplified timeout handler - only check if we already have results.
        """
        try:
            # Check if we already have probe results (timeout may be stale)
            if self.probe_result is not None:
                self.logger.debug("Probe timeout triggered but already have results - ignoring")
                return
                
            self.logger.warning("Probe result timeout")
            
            # Disconnect probe tracking to prevent further signals
            self._disconnect_probe_tracking()
            
            # Clean up timeout timer
            if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
                self.probe_timeout_timer.stop()
                self.probe_timeout_timer = None
            
            # Show retry/cancel dialog
            result = dialog.RetryCancel(
                parent=self,
                text="Probe Timeout\n\nFailed to receive probe test results.\n\nThis might happen due to communication issues or probe problems.\n\nWould you like to retry the probe test or cancel calibration?",
                overlay=True,
                icon="warning"
            )
            
            if result == "retry":
                # Retry probe sequence
                self.logger.info("User chose to retry probe test")
                # Reset state before retrying
                self.probe_result = None
                self.probe_average_z = None
                QTimer.singleShot(1000, self.start_probe_sequence)
            else:
                # Cancel - exit the wizard entirely
                self.logger.info("User cancelled calibration due to probe timeout")
                # Just call on_cancel_clicked which handles cleanup and exit
                self.on_cancel_clicked()
                
        except Exception as e:
            self.logger.error(f"Error handling probe timeout: {e}")
            # Call on_cancel_clicked which handles cleanup and exit
            self.on_cancel_clicked()

    def _handle_position_timeout(self):
        """
        Handle position recording timeout with user interaction.
        
        Simplified timeout handler - only check if we already have position.
        """
        try:
            # Check if we already have position data (timeout may be stale)
            if self.manual_position is not None:
                self.logger.debug("Position timeout triggered but already have position - ignoring")
                return
                
            self.logger.warning("Position recording timeout")
            
            # Disconnect position tracking to prevent further signals
            self._disconnect_position_tracking()
            
            # Clean up timeout timer
            if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
                self.position_timeout_timer.stop()
                self.position_timeout_timer = None
            
            # Show retry/cancel dialog
            result = dialog.RetryCancel(
                parent=self,
                text="Position Recording Timeout\n\nFailed to get current position from M114 command.\n\nThis might happen due to communication issues.\n\nWould you like to retry position recording or cancel calibration?",
                overlay=True,
                icon="warning"
            )
            
            if result == "retry":
                # Retry position recording
                self.logger.info("User chose to retry position recording")
                # Reset state before retrying
                self.manual_position = None
                self.manual_z = None
                QTimer.singleShot(1000, self.record_manual_position)
            else:
                # Cancel - exit the wizard entirely
                self.logger.info("User cancelled calibration due to position timeout")
                # Just call on_cancel_clicked which handles cleanup and exit
                self.on_cancel_clicked()
                
        except Exception as e:
            self.logger.error(f"Error handling position timeout: {e}")
            # Call on_cancel_clicked which handles cleanup and exit
            self.on_cancel_clicked()

    # ==================== VIDEO PLAYBACK MANAGEMENT ====================

    def _play_calibration_video(self):
        """
        Start playing the calibration instruction video.
        
        Loads and plays the paper calibration GIF in the designated label.
        """
        try:
            if not self.step1Gif:
                self.logger.warning("No GIF label found for video playback")
                return
                
            # Stop any existing video
            self._stop_current_video()
            
            # Load the calibration GIF
            gif_path = os.path.join(os.path.dirname(__file__), "1_Paper Calibration.gif")
            
            if os.path.exists(gif_path):
                self.current_movie = QMovie(gif_path)
                self.current_movie.setCacheMode(QMovie.CacheNone)  # Avoid loading entire GIF into memory
                self.step1Gif.setMovie(self.current_movie)
                self.current_movie.start()
                self.logger.info("Started playing calibration video")
            else:
                self.logger.warning(f"Calibration GIF not found at: {gif_path}")
                # Show placeholder text
                self.step1Gif.setText("Calibration Video\n(File not found)")
                
        except Exception as e:
            self.logger.error(f"Error playing calibration video: {e}")
            # Show placeholder on error
            if self.step1Gif:
                self.step1Gif.setText("Calibration Video\n(Error loading)")

    def _stop_current_video(self):
        """
        Stop the current video playback and clean up resources.
        """
        try:
            if hasattr(self, 'current_movie') and self.current_movie:
                self.current_movie.stop()
                self.current_movie = None
                self.logger.debug("Stopped current video playback")
        except Exception as e:
            self.logger.error(f"Error stopping video: {e}")

    # ==================== STATE MANAGEMENT AND CLEANUP ====================

    def _reset_wizard_state(self):
        """
        Reset all wizard state variables to initial values.
        
        Performs complete state cleanup including signal disconnections,
        step reset, and data clearing. This is called when the wizard
        is opened to ensure clean starting state. 
        
        ⚠️  DO NOT call this when exiting/canceling - use cleanup() instead!
        """
        # Core resource cleanup (shared pattern)
        self._cleanup_core_resources()
        
        # Reset to welcome step (only for wizard restart, not exit!)
        self.goto_step(self.STEP_WELCOME)
        
        # Reset wizard-specific state variables
        self._reset_state_variables()

    def cleanup(self):
        """
        Cleanup resources WITHOUT restarting the wizard.
        
        Use this when canceling, exiting, or handling errors where
        you want to clean up but NOT restart the wizard.
        """
        # Core resource cleanup only - no goto_step call
        self._cleanup_core_resources()
        
        # Reset state variables only - no wizard restart
        self._reset_state_variables()

    def _reset_state_variables(self):
        """Reset state variables to initial values."""
        self.probe_result = None
        self.manual_position = None
        self.probe_average_z = None
        self.manual_z = None
        self.calculated_offset = None
        self.calibration_complete = False

    def _cleanup_core_resources(self):
        """
        Cleanup core resources (signals, timers, videos).
        
        This is the shared cleanup logic for consistent resource management.
        """
        # Disconnect all tracking
        self._disconnect_probe_tracking()
        self._disconnect_position_tracking()
        
        # Stop any video playback
        self._stop_current_video()
        
        # Clean up timeout timers with proper null checking
        if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
            self.probe_timeout_timer.stop()
            self.probe_timeout_timer = None
            
        if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
            self.position_timeout_timer.stop()
            self.position_timeout_timer = None

    # ==================== UTILITY AND HELPER METHODS ====================

    def _assess_probe_quality(self, std_deviation):
        """
        Assess probe quality based on standard deviation.
        
        Args:
            std_deviation (float): Standard deviation from probe results
            
        Returns:
            str: Quality assessment string
        """
        if std_deviation < self.QUALITY_EXCELLENT:
            return 'Excellent'
        elif std_deviation < self.QUALITY_GOOD:
            return 'Good'
        elif std_deviation < self.QUALITY_ACCEPTABLE:
            return 'Acceptable'
        else:
            return 'Poor'

    def _show_error(self, title, message):
        """
        Show error dialog with consistent styling.
        
        Args:
            title (str): Error dialog title
            message (str): Error message content
        """
        self.logger.error(f"{title}: {message}")
        dialog.WarningOk(self, f"{title}\n\n{message}", overlay=True)

    # ==================== SIGNAL CONNECTION MANAGEMENT ====================

    def _connect_probe_tracking(self):
        """
        Connect probe tracking for receiving probe results.
        
        Establishes connection to the printer model's probe_accuracy_result_received signal.
        """
        if self._probe_tracking_connected:
            self.logger.debug("Probe tracking already connected - skipping")
            return
            
        if not self.model:
            self.logger.error("No printer model available for probe tracking")
            return
            
        try:
            self.model.probe_accuracy_result_received.connect(self.on_probe_result_received)
            self._probe_tracking_connected = True
            self.logger.info("Probe tracking connected successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect probe tracking: {e}")
            raise
    
    def _disconnect_probe_tracking(self):
        """
        Disconnect probe tracking when no longer needed.
        """
        if not self._probe_tracking_connected:
            self.logger.debug("Probe tracking already disconnected - skipping")
            return
            
        if not self.model:
            self.logger.debug("No model available for probe tracking disconnect")
            self._probe_tracking_connected = False
            return
            
        try:
            self.model.probe_accuracy_result_received.disconnect(self.on_probe_result_received)
            self._probe_tracking_connected = False
            self.logger.info("Probe tracking disconnected successfully")
        except (TypeError, AttributeError) as e:
            self._probe_tracking_connected = False
            self.logger.debug(f"Probe tracking was already disconnected: {e}")
        except Exception as e:
            self.logger.error(f"Error disconnecting probe tracking: {e}")
            self._probe_tracking_connected = False

    def _connect_position_tracking(self):
        """
        Connect position tracking for receiving M114 responses.
        """
        if self._position_tracking_connected:
            self.logger.debug("Position tracking already connected - skipping")
            return
            
        if not self.model:
            self.logger.error("No printer model available for position tracking")
            return
            
        try:
            self.model.current_position_updated.connect(self.on_position_updated)
            self._position_tracking_connected = True
            self.logger.info("Position tracking connected successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect position tracking: {e}")
            raise
    
    def _disconnect_position_tracking(self):
        """
        Disconnect position tracking when no longer needed.
        """
        if not self._position_tracking_connected:
            self.logger.debug("Position tracking already disconnected - skipping")
            return
            
        if not self.model:
            self.logger.debug("No model available for position tracking disconnect")
            self._position_tracking_connected = False
            return
            
        try:
            self.model.current_position_updated.disconnect(self.on_position_updated)
            self._position_tracking_connected = False
            self.logger.info("Position tracking disconnected successfully")
        except (TypeError, AttributeError) as e:
            self._position_tracking_connected = False
            self.logger.debug(f"Position tracking was already disconnected: {e}")
        except Exception as e:
            self.logger.error(f"Error disconnecting position tracking: {e}")
            self._position_tracking_connected = False
