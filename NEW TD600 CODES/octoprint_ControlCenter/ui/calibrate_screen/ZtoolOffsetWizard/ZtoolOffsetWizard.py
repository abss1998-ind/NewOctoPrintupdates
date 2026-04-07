"""
Z Tool Offset Calibration Wizard
================================

Automated Z tool offset calibration wizard for IDEX printers using probe accuracy testing.

Architecture:
- MVP pattern with model signals for probe result communication
- 2-step wizard: Welcome → Automated Calibration
- Timeout handling for robust probe operation failure recovery
- Proper offset calculation that adds to existing offsets rather than replacing

Workflow:
1. Welcome - Introduction and preparation (homing, tool offset retrieval)
2. Calibration - Automated probe sequence for both tools with quality assessment

Features:
- Automatic probe sequencing with proper tool switching
- Quality assessment based on standard deviation
- Timeout handling with retry/cancel options
- Proper offset calculation preserving existing values
- Comprehensive error handling and user feedback

Dependencies:
- OctoPrint client for G-code commands
- Printer model for probe result signals and current offset retrieval
- PyQt5 UI framework with custom dialog utilities
"""

import os
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QLabel
from PyQt5.QtCore import QTimer
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import dialog
import time


class ZtoolOffsetWizard(QWidget):
    """
    Z Tool Offset Calibration Wizard
    ===============================
    
    Automated calibration wizard for Z tool offsets using probe accuracy testing.
    
    This wizard provides a streamlined 2-step process:
    1. Welcome - Introduction, preparation, and axis homing
    2. Calibration - Automated probe sequence for both tools with quality assessment
    
    Key Features:
    - Automatic probe sequencing with proper tool switching and positioning
    - Quality assessment based on probe standard deviation
    - Timeout handling for probe operation failures
    - Proper offset calculation that preserves existing offset values
    - Comprehensive error handling with user-friendly feedback
    
    Architecture:
    - Uses MVP pattern with model signals for probe result communication
    - Timeout-based error recovery for robust operation
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
    STEP_CALIBRATION = 1
    TOTAL_STEPS = 2
    
    # Timeout configuration
    PROBE_TIMEOUT_SECONDS = 30  # Timeout for probe operations
    
    # Quality thresholds for probe standard deviation (mm)
    QUALITY_EXCELLENT = 0.01
    QUALITY_GOOD = 0.02
    QUALITY_ACCEPTABLE = 0.05

    # ==================== INITIALIZATION AND SETUP ====================

    def __init__(self, main_window):
        """
        Initialize the Z Tool Offset Wizard.
        
        Sets up UI components, state variables, and signal connections for the automated
        Z tool offset calibration process.
        
        Args:
            main_window: Main application window providing access to printer model and OctoPrint client
        """
        super().__init__()
        self.main_window = main_window
        self.model = main_window.printer_model
        self.octoprint_client = main_window.octoprint_client
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing Z Tool Offset Wizard")

        # Initialize state variables
        self._init_state_variables()
        
        # Load UI and initialize components
        self._load_ui()
        self._init_ui_components()
        self._connect_signals()

        self.logger.info("Z Tool Offset Wizard initialized successfully")

    def _init_state_variables(self):
        """
        Initialize all state tracking variables.
        
        Sets up probe result storage, signal connection tracking, wizard navigation state,
        and timeout handling variables.
        """
        # Probe result storage
        self.probe_results = {
            'tool0': None,  # Will store complete probe data dict
            'tool1': None   # Will store complete probe data dict
        }
        self.current_probing_tool = None    # Currently active probing tool
        self.probe_data_collected = False   # Flag indicating if calibration is complete
        self.calculated_z_offset = None     # Calculated Z offset ready for application

        # Signal connection tracking
        self._probe_tracking_connected = False

        # Wizard navigation state
        self._current_step = 0
        
        # Probe timeout handling
        self.probe_timeout_timer = None         # QTimer for probe operation timeouts

    def _load_ui(self):
        """
        Load the UI file with proper error handling.
        
        Raises:
            Exception: If UI file cannot be loaded
        """
        try:
            ui_file_path = os.path.join(os.path.dirname(__file__), "ZtoolOffsetWizard.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("ZtoolOffsetWizard UI loaded successfully")
        except Exception as e:
            self.logger.exception(f"Failed to load ZtoolOffsetWizard UI file: {e}")
            raise

    def _init_ui_components(self):
        """
        Initialize and validate all UI components.
        
        Finds all required UI elements and validates their existence for robust operation.
        """
        # Main navigation components
        self.stackedWidget = self.findChild(QStackedWidget, "stackedWidget")
        self.welcomePage = self.findChild(QWidget, "welcomePage")
        self.calibrationPage = self.findChild(QWidget, "calibrationPage")
        
        # Labels for user feedback
        self.stepLabel = self.findChild(QLabel, "stepLabel")
        self.calibrationLabel = self.findChild(QLabel, "calibrationLabel")

        # Navigation buttons
        self.nextButton = self.findChild(QPushButton, "nextButton")
        self.cancelButton = self.findChild(QPushButton, "cancelButton1")

        # Validate all required UI components exist
        required_components = [
            self.stackedWidget, self.welcomePage, self.calibrationPage,
            self.nextButton, self.cancelButton, self.stepLabel, self.calibrationLabel
        ]
        check_ui_elements(self, required_components, "ZtoolOffsetWizard")

    def _connect_signals(self):
        """
        Connect all signal handlers.
        
        Sets up button connections and prepares for model signal connections.
        Note: probe_accuracy_result_received signal is connected only when needed
        during probe sequence for proper resource management.
        """
        # Button connections
        if self.nextButton:
            self.nextButton.clicked.connect(self.on_next_clicked)
        if self.cancelButton:
            self.cancelButton.clicked.connect(self.on_cancel_clicked)

    # ==================== WIZARD LIFECYCLE AND NAVIGATION ====================

    def showEvent(self, event):
        """
        Handle wizard activation - reset state and prepare printer.
        
        Called when the wizard widget becomes visible. Resets wizard to welcome step,
        retrieves current tool offsets, and homes the printer for consistent starting position.
        
        Args:
            event: Qt show event
        """
        super().showEvent(event)
        try:
            # Reset all wizard state variables and disconnect any existing connections
            self._reset_wizard_state()
            
            self.logger.info("Z Tool Offset calibration started - getting latest tool offsets and homing")
            
            # Validate we have necessary components
            if not self.octoprint_client:
                self.logger.error("No OctoPrint client available")
                self._show_error("Connection Error", "No OctoPrint client available. Please check connection.")
                return
                
            if not self.model:
                self.logger.error("No printer model available")
                self._show_error("Model Error", "No printer model available. Please restart the application.")
                return
            
            # Get latest M218 tool offsets from printer (similar to camera wizard)
            self.octoprint_client.gcode(command='M503')
            
            # Home all axes for consistent starting position
                        # Heat both nozzles to 80C
            self.octoprint_client.gcode("M104 T0 S180")
            self.octoprint_client.gcode("M104 T1 S180")
            self.octoprint_client.home(['x', 'y', 'z'])
            self.octoprint_client.jog(x=0, y=0, z=5, absolute=True, speed=9000)  # Raise Z slightly
            
        except Exception as e:
            self.logger.error(f"Error in ZtoolOffsetWizard showEvent: {e}")
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
            elif index == self.STEP_CALIBRATION:
                self.stackedWidget.setCurrentWidget(self.calibrationPage)
        
        # Update step indicator
        self._update_step_label()

        # Execute step-specific setup
        if index == self.STEP_WELCOME:
            self._setup_welcome_step()
        elif index == self.STEP_CALIBRATION:
            self._setup_calibration_step()

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
        
        Sets up the initial welcome interface with appropriate button text and state.
        """
        try:
            if self.nextButton:
                self.nextButton.setText("Start Calibration")
                self.nextButton.setEnabled(True)
        except Exception as e:
            self.logger.error(f"Error setting up welcome step: {e}")

    def _setup_calibration_step(self):
        """
        Configure UI and start the automated calibration process.
        
        Connects probe tracking, updates UI to processing state, and initiates the
        automated probe sequence after a short delay to ensure signal connections are ready.
        """
        try:
            # Disconnect any existing probe tracking before connecting new one
            self._disconnect_probe_tracking()
            
            # Connect probe tracking FIRST before starting any probe operations
            self._connect_probe_tracking()
            
            # Update button to processing state
            if self.nextButton:
                self.nextButton.setText("Processing...")
                self.nextButton.setEnabled(False)
            
            # Show initial status
            if self.calibrationLabel:
                self.calibrationLabel.setText(
                    "🔧 Initializing Z Tool Offset Calibration...\n\n"
                    "• Preparing automated probe sequence\n"
                    "• Both tools will be calibrated automatically\n"
                    "• Please wait while the system measures tool heights\n\n"
                    "Status: Starting calibration..."
                )
            
            self.logger.info("Starting automated probe sequence")
            # Use QTimer to ensure signal connection is complete before starting probe sequence
            QTimer.singleShot(100, self.start_probe_sequence)
            
        except Exception as e:
            self.logger.error(f"Error setting up calibration step: {e}")
            self._show_error("Error starting calibration", str(e))

    # ==================== USER INTERACTION HANDLERS ====================

    def on_next_clicked(self):
        """
        Handle next button clicks with step-based navigation and validation.
        
        Provides different behavior based on current wizard step:
        - Welcome: Validate components and advance to calibration step
        - Calibration: Finish calibration (only if probe data is collected)
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
                # Move to calibration step
                self.goto_step(self.STEP_CALIBRATION)
            elif self._current_step == self.STEP_CALIBRATION:
                # Only allow finishing if calibration is complete
                if self.probe_data_collected:
                    self.finish_calibration()
                else:
                    dialog.WarningOk(self, "Please wait for probe calibration to complete.", overlay=True)
                    
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
            
            # Return to tool 0 and home
            if self.octoprint_client:
                self.octoprint_client.home(['x', 'y', 'z'])
                self.octoprint_client.gcode("M104 T0 S0")
                self.octoprint_client.gcode("M104 T1 S0")
            
            # Return to main calibration screen
            if hasattr(self.main_window, 'calibrate_screen'):
                self.main_window.calibrate_screen.show_calibrate_screen()
            
        except Exception as e:
            self.logger.error(f"Error in on_cancel_clicked: {e}")
            # Still try to return to main screen even if there's an error
            if hasattr(self.main_window, 'calibrate_screen'):
                self.main_window.calibrate_screen.show_calibrate_screen()

    # ==================== AUTOMATED PROBE SEQUENCE ====================

    def start_probe_sequence(self):
        """
        Initialize and start the automated probe sequence for both tools.
        
        Resets probe state, updates UI with progress information, and begins the
        sequence with Tool 0. The sequence will automatically proceed to Tool 1
        after Tool 0 completes successfully.
        """
        try:
            self.logger.info("Starting automated probe sequence")
            
            # Reset probe state (probe tracking is already connected in _setup_calibration_step)
            self._reset_state_variables()
            
            # Stop any existing timeout timers
            if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
                self.probe_timeout_timer.stop()
                self.probe_timeout_timer = None
                self.logger.debug("Cleaned up existing probe timeout timer")
            
            # Update UI with detailed progress information
            if self.calibrationLabel:
                self.calibrationLabel.setText(
                    "📍 Starting Tool 0 Calibration\n\n"
                    "• Switching to Tool 0\n"
                    "• Moving to bed center\n"
                    "• Preparing probe accuracy test\n\n"
                    "Status: Initializing Tool 0..."
                )
            
            # Begin with Tool 0
            self.probe_tool(0)
            
        except Exception as e:
            self.logger.error(f"Error starting probe sequence: {e}")
            self._show_error("Probe Sequence Error", str(e))

    def probe_tool(self, tool_number):
        """
        Probe a specific tool with proper sequencing.
        
        Handles tool switching, positioning, and probe initiation for the specified tool.
        Uses timed sequencing to ensure proper tool switching before movement and probing.
        
        Args:
            tool_number (int): Tool number to probe (0 or 1)
        """
        try:
            tool_name = f'tool{tool_number}'
            
            # Check if we already have results for this tool
            if self.probe_results.get(tool_name) is not None:
                self.logger.warning(f"Already have probe results for {tool_name} - skipping duplicate probe operation")
                return
            
            self.logger.info(f"Probing tool {tool_number}")
            self.current_probing_tool = tool_name
            
            # Update status for current tool being probed
            tool_desc = "Tool 0" if tool_number == 0 else "Tool 1"
            if self.calibrationLabel:
                self.calibrationLabel.setText(f"📍 {tool_desc} Probing in Progress\n\n" +
                                            f"• {tool_desc} selected and positioned\n" +
                                            f"• Running probe accuracy test\n" +
                                            f"• Collecting measurement data\n\n" +
                                            f"Status: Switching to {tool_desc}...")
            
            # Switch to the specified tool
            self.octoprint_client.gcode(command=f'T{tool_number}')
            
            # Calculate bed center position
            build_size = getattr(self.model, 'machineBuildSize', {'X': 300, 'Y': 300}) if self.model else {'X': 300, 'Y': 300}
            center_x = int(build_size.get('X', 300) / 2)  # Center of bed X
            center_y = int(build_size.get('Y', 300) / 2)  # Center of bed Y
            
            self.logger.info(f"Using bed size: {build_size.get('X')}x{build_size.get('Y')}mm, probing at center X{center_x} Y{center_y}")
            
            # Use QTimer for proper sequencing - wait for tool switch to complete
            QTimer.singleShot(3000, lambda: self._move_and_probe(tool_number, center_x, center_y))
            
        except Exception as e:
            self.logger.error(f"Error probing tool {tool_number}: {e}")
            dialog.WarningOk(self, f"Error probing tool {tool_number}: {str(e)}", overlay=True)

    def _move_and_probe(self, tool_number, center_x, center_y):
        """
        Move to position and start probing after tool switch completes.
        
        Args:
            tool_number (int): Tool number being probed
            center_x (int): X coordinate for probe position
            center_y (int): Y coordinate for probe position
        """
        try:
            tool_name = f'tool{tool_number}'
            
            # Double-check we should still be probing this tool
            if self.probe_results.get(tool_name) is not None:
                self.logger.warning(f"Already have probe results for {tool_name} - skipping movement and probe")
                return
            
            self.logger.info(f"Moving tool {tool_number} to probe position")
            
            # Update status
            tool_desc = "Tool 0" if tool_number == 0 else "Tool 1"
            if self.calibrationLabel:
                self.calibrationLabel.setText(f"📍 {tool_desc} Probing in Progress\n\n" +
                                            f"• {tool_desc} selected and positioned\n" +
                                            f"• Moving to probe position\n" +
                                            f"• Collecting measurement data\n\n" +
                                            f"Status: Moving to probe position...")
            
            # Move to center position
            self.octoprint_client.jog(x=center_x, y=center_y, z=5, absolute=True, speed=8000)

            # Start probing after movement delay
            QTimer.singleShot(2000, lambda: self._start_probe_accuracy(tool_number))
            
        except Exception as e:
            self.logger.error(f"Error moving tool {tool_number} to probe position: {e}")
            dialog.WarningOk(self, f"Error moving tool {tool_number}: {str(e)}", overlay=True)

    def _start_probe_accuracy(self, tool_number):
        """
        Start the probe accuracy test with timeout handling.
        
        Initiates the PROBE_ACCURACY command and sets up timeout monitoring to handle
        cases where probe results are not received within the expected timeframe.
        
        Args:
            tool_number (int): Tool number being probed (0 or 1)
        """
        try:
            tool_name = f'tool{tool_number}'
            
            # Final check - ensure we should still be probing this tool
            if self.probe_results.get(tool_name) is not None:
                self.logger.warning(f"Already have probe results for {tool_name} - skipping probe accuracy test")
                return
            
            self.logger.info(f"Starting probe accuracy test for tool {tool_number}")
            
            # Update status
            tool_desc = "Tool 0" if tool_number == 0 else "Tool 1"
            if self.calibrationLabel:
                self.calibrationLabel.setText(f"📍 {tool_desc} Probing in Progress\n\n" +
                                            f"• {tool_desc} selected and positioned\n" +
                                            f"• Running probe accuracy test\n" +
                                            f"• Collecting measurement data\n\n" +
                                            f"Status: Probing {tool_desc}... Please wait.")
            
            # Set up timeout for probe result
            if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
                self.probe_timeout_timer.stop()
                self.logger.debug("Stopped existing probe timeout timer")
            
            self.probe_timeout_timer = QTimer()
            self.probe_timeout_timer.setSingleShot(True)
            self.probe_timeout_timer.timeout.connect(lambda: self._handle_probe_timeout(tool_number))
            self.probe_timeout_timer.start(self.PROBE_TIMEOUT_SECONDS * 1000)  # Convert to milliseconds
            self.logger.info(f"Started probe timeout timer for tool {tool_number} ({self.PROBE_TIMEOUT_SECONDS} seconds)")
            
            # Run probe accuracy macro with specified speed
            self.logger.info(f"Running PROBE_ACCURACY PROBE_SPEED=3 for tool {tool_number}")
            self.octoprint_client.gcode(command='PROBE_ACCURACY PROBE_SPEED=3')
            
        except Exception as e:
            self.logger.error(f"Error starting probe accuracy for tool {tool_number}: {e}")
            dialog.WarningOk(self, f"Error starting probe for tool {tool_number}: {str(e)}", overlay=True)

    # ==================== PROBE RESULT PROCESSING ====================

    def on_probe_result_received(self, tool_name, probe_data):
        """
        Handle probe result signals from the printer model.
        
        Simplified approach: Use current_probing_tool instead of complex tool checking.
        This matches the approach used in the camera tool offset wizard.
        
        Args:
            tool_name (str): Tool identifier from printer model (may not be accurate)
            probe_data (dict): Complete probe data with keys: maximum, minimum, range, 
                             average, median, standard_deviation
        """
        try:
            self.logger.info(f"🔍 PROBE RESULT RECEIVED: current_probing_tool={self.current_probing_tool}, data={probe_data}")
            
            # Use current_probing_tool instead of tool_name from signal - this is more reliable
            if not self.current_probing_tool:
                self.logger.warning("❌ Received probe result but no current_probing_tool set - ignoring")
                return
            
            # Check if we already have results for this tool to prevent duplicates
            if self.probe_results.get(self.current_probing_tool) is not None:
                self.logger.warning(f"❌ Already have probe results for {self.current_probing_tool} - ignoring duplicate")
                return
            
            # Cancel timeout timer since we got a probe result
            if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
                self.probe_timeout_timer.stop()
                self.probe_timeout_timer = None
                self.logger.debug("Probe timeout timer stopped successfully")
            
            # Store the complete probe data for the current probing tool
            if self.current_probing_tool in self.probe_results:
                self.probe_results[self.current_probing_tool] = probe_data
                
                # Get the average value for display and calculations
                average_value = probe_data.get('average', 0.0)
                std_dev = probe_data.get('standard_deviation', 0.0)
                
                # Determine quality based on standard deviation
                quality = self._assess_probe_quality(std_dev)
                
                # Update UI and proceed based on which tool was just probed
                if self.current_probing_tool == 'tool0' and self.probe_results['tool1'] is None:
                    # Tool 0 done, now probe tool 1
                    self.logger.info("Tool 0 probing complete via signal, starting tool 1")
                    if self.calibrationLabel:
                        self.calibrationLabel.setText(f"✅ Tool 0 Complete!\n\n" +
                                                    f"• Average: {average_value:.6f}mm\n" +
                                                    f"• Std Dev: {std_dev:.6f}mm\n" +
                                                    f"• Quality: {quality}\n\n" +
                                                    f"📍 Preparing Tool 1 calibration...")
                    
                    # Use QTimer instead of blocking sleep to start tool 1 probing
                    self.logger.info("Waiting 2 seconds before probing tool 1...")
                    QTimer.singleShot(2000, lambda: self.probe_tool(1))
                    
                elif self.current_probing_tool == 'tool1':
                    # Both tools done, disconnect tracking and calculate offset
                    self.logger.info("Tool 1 probing complete via signal, calculating offset")
                    
                    # Disconnect probe tracking since we're done with all probing
                    self._disconnect_probe_tracking()
                    
                    if self.calibrationLabel:
                        self.calibrationLabel.setText(f"✅ Tool 1 Complete!\n\n" +
                                                    f"• Average: {average_value:.6f}mm\n" +
                                                    f"• Std Dev: {std_dev:.6f}mm\n" +
                                                    f"• Quality: {quality}\n\n" +
                                                    f"🔄 Calculating final Z offset...")
                    # Use QTimer to ensure UI updates before calculation
                    QTimer.singleShot(500, self.calculate_z_offset)
            else:
                self.logger.error(f"Unexpected current_probing_tool: {self.current_probing_tool}")
                
        except Exception as e:
            self.logger.error(f"Error in on_probe_result_received: {e}")
            # Disconnect probe tracking on error to prevent memory leaks
            self._disconnect_probe_tracking()
            dialog.WarningOk(self, f"Error processing probe result: {str(e)}", overlay=True)

    # ==================== TIMEOUT AND ERROR HANDLING ====================

    def _handle_probe_timeout(self, tool_number):
        """
        Handle probe result timeout with user interaction.
        
        Simplified timeout handler without complex tool checking.
        
        Args:
            tool_number (int): Tool number that timed out (0 or 1)
        """
        try:
            tool_name = f'tool{tool_number}'
            
            # Check if we already have results for this tool (timeout may be stale)
            if self.probe_results.get(tool_name) is not None:
                self.logger.debug(f"Probe timeout triggered but already have results for {tool_name} - ignoring")
                return
                
            self.logger.warning(f"Probe result timeout for tool {tool_number}")
            
            # Disconnect probe tracking to prevent further signals
            self._disconnect_probe_tracking()
            
            # Clean up timeout timer
            if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
                self.probe_timeout_timer.stop()
                self.probe_timeout_timer = None
            
            # Show dialog asking user what to do
            tool_desc = "Tool 0" if tool_number == 0 else "Tool 1"
            result = dialog.RetryCancel(
                parent=self,
                text=f"Probe Timeout for {tool_desc}\n\nFailed to receive probe results for {tool_desc}.\n\nThis might happen due to communication issues or probe problems.\n\nWould you like to retry the probe or cancel calibration?",
                overlay=True,
                icon="warning"
            )
            
            if result == "retry":
                # Retry probing the same tool
                self.logger.info(f"User chose to retry probing for tool {tool_number}")
                # Reset state before retrying
                tool_name = f'tool{tool_number}'
                self.probe_results[tool_name] = None
                QTimer.singleShot(1000, lambda: self.probe_tool(tool_number))
            else:
                # Cancel - exit the wizard entirely
                self.logger.info(f"User cancelled calibration due to probe timeout for tool {tool_number}")
                # Just call on_cancel_clicked which handles cleanup and exit
                self.on_cancel_clicked()
                
        except Exception as e:
            self.logger.error(f"Error handling probe timeout: {e}")
            # Call on_cancel_clicked which handles cleanup and exit
            self.on_cancel_clicked()

    # ==================== OFFSET CALCULATION AND APPLICATION ====================

    def calculate_z_offset(self):
        """
        Calculate the Z offset between tools using complete probe data.
        
        Performs comprehensive offset calculation including quality assessment,
        current offset preservation, and detailed result presentation to the user.
        Enables the apply button once calculation is complete.
        """
        try:
            if self.probe_results['tool0'] is not None and self.probe_results['tool1'] is not None:
                tool0_data = self.probe_results['tool0']
                tool1_data = self.probe_results['tool1']
                
                # Extract average values for offset calculation
                tool0_avg = tool0_data.get('average', 0.0)
                tool1_avg = tool1_data.get('average', 0.0)
                raw_z_diff =  tool1_avg - tool0_avg
                
                # Get current Z tool offset from printer model
                current_z_offset = self._get_current_z_offset()
                
                # Calculate new Z offset (current + measured difference)
                new_z_offset = round(raw_z_diff, 3)
                
                # Store calculated offset for use in finish_calibration
                self.calculated_z_offset = new_z_offset
                
                # Extract standard deviations for quality assessment
                tool0_std = tool0_data.get('standard_deviation', 0.0)
                tool1_std = tool1_data.get('standard_deviation', 0.0)
                
                self.logger.info(f"Probe results - Tool 0: avg={tool0_avg:.6f}, std={tool0_std:.6f}")
                self.logger.info(f"Probe results - Tool 1: avg={tool1_avg:.6f}, std={tool1_std:.6f}")
                self.logger.info(f"Raw Z difference (T0-T1): {raw_z_diff:.6f}")
                self.logger.info(f"Current Z offset: {current_z_offset:.3f}")
                self.logger.info(f"New Z offset to apply: {new_z_offset:.3f}")
                
                # Determine quality indicators using helper method
                tool0_quality = self._assess_probe_quality(tool0_std)
                tool1_quality = self._assess_probe_quality(tool1_std)
                
                # Update UI with comprehensive results including offset information
                self.calibrationLabel.setText(f"PROBE RESULTS:\n" +
                                            f"Tool 0: {tool0_avg:.6f}mm (±{tool0_std:.6f}) [{tool0_quality}]\n" +
                                            f"Tool 1: {tool1_avg:.6f}mm (±{tool1_std:.6f}) [{tool1_quality}]\n\n" +
                                            f"HEIGHT DIFFERENCE:\n" +
                                            f"Raw Difference (T0-T1): {raw_z_diff:.6f}mm\n\n" +
                                            f"Z TOOL OFFSETS:\n" +
                                            f"Current Z Offset: {current_z_offset:.3f}mm\n" +
                                            f"New Z Offset: {new_z_offset:.3f}mm\n\n" +
                                            f"Click 'Apply Offset' to save and return to menu.")
                
                # Enable the finish button with new text
                if self.nextButton:
                    self.nextButton.setText("Apply Offset")
                    self.nextButton.setEnabled(True)
                
                # Mark data as collected
                self.probe_data_collected = True
                self.logger.info(f"Z offset calculation complete: raw_diff={raw_z_diff:.6f}mm, new_offset={new_z_offset:.3f}mm")
            else:
                self.logger.warning("Cannot calculate Z offset - missing probe data for one or both tools")
                
        except Exception as e:
            self.logger.error(f"Error in calculate_z_offset: {e}")
            dialog.WarningOk(self, f"Error calculating Z offset: {str(e)}", overlay=True)

    def apply_z_offset(self, z_offset):
        """
        Apply the calculated Z offset to the printer configuration.
        
        Sends M218 command to set the tool offset and saves to EEPROM using M500.
        
        Args:
            z_offset (float): Z offset value to apply in millimeters
        """
        try:
            self.logger.info(f"Applying Z offset: {z_offset:.3f}")
            
            # Set the tool offset using M218 command
            offset_command = f"M218 T1 Z{z_offset:.3f}"
            self.logger.info(f"Setting tool Z offset with command: {offset_command}")
            self.octoprint_client.gcode(command=offset_command)
            
            # Save to EEPROM
            self.octoprint_client.gcode(command='M500')
            
            self.logger.info(f"Z offset {z_offset:.3f} applied and saved to EEPROM")
            
        except Exception as e:
            self.logger.error(f"Error applying Z offset: {e}")
            dialog.WarningOk(self, f"Error applying Z offset: {str(e)}", overlay=True)

    def finish_calibration(self):
        """
        Complete the calibration process and return to main screen.
        
        Applies the calculated Z offset, performs cleanup, and navigates back to
        the main calibration screen with proper printer state restoration.
        """
        self.logger.info("ZtoolOffsetWizard.finish_calibration started")
        try:
            # Disconnect probe tracking since calibration is complete
            self._disconnect_probe_tracking()
            
            # Update status to show applying offset
            if self.calibrationLabel:
                self.calibrationLabel.setText(
                    "• APPLYING Z OFFSET...\n\n"
                    "• Saving offset to printer configuration\n"
                    "• Writing to EEPROM\n"
                    "• Returning to Tool 0\n"
                    "• Homing axes\n\n"
                    "Please wait..."
                )
            
            # Disable button during application
            if self.nextButton:
                self.nextButton.setEnabled(False)
                self.nextButton.setText("Applying...")
            
            # Apply the calculated Z offset if available
            if hasattr(self, 'calculated_z_offset') and self.calculated_z_offset is not None:
                self.logger.info(f"Applying previously calculated Z offset: {self.calculated_z_offset:.3f}mm")
                self.apply_z_offset(self.calculated_z_offset)
            else:
                self.logger.warning("Cannot apply Z offset - missing probe data")
            
            # Return to tool 0 and home
            if self.octoprint_client:
                self.octoprint_client.home(['x', 'y', 'z'])
                self.octoprint_client.gcode("M104 T0 S0")
                self.octoprint_client.gcode("M104 T1 S0")

            # Return to main calibration screen
            if hasattr(self.main_window, 'calibrate_screen'):
                self.main_window.calibrate_screen.show_calibrate_screen()
            
        except Exception as e:
            self.logger.error(f"Error in ZtoolOffsetWizard.finish_calibration: {e}")
            self._show_error("Calibration Finish Error", str(e))

    # ==================== STATE MANAGEMENT AND CLEANUP ====================

    def _reset_wizard_state(self):
        """
        Reset all wizard state variables to initial values.
        
        Performs complete state cleanup including probe tracking disconnection,
        step reset, and probe data clearing. This is called when the wizard
        is opened to ensure clean starting state.
        
        ⚠️  DO NOT call this when exiting/canceling - use cleanup() instead!
        """
        # Core resource cleanup (signals and timers)
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
        """
        Reset probe-related state variables to initial values.
        
        Clears all probe results, resets collection flags, and resets
        probing state for clean wizard restart.
        """
        self.probe_results = {'tool0': None, 'tool1': None}
        self.probe_data_collected = False
        self.current_probing_tool = None
        self.calculated_z_offset = None

    def _cleanup_core_resources(self):
        """
        Cleanup core resources (signals and timers).
        
        This is the shared cleanup logic used by _reset_wizard_state()
        and potentially other cleanup methods.
        """
        # Disconnect probe tracking if connected
        self._disconnect_probe_tracking()
        
        # Clean up timeout timer with proper null checking
        if hasattr(self, 'probe_timeout_timer') and self.probe_timeout_timer:
            self.probe_timeout_timer.stop()
            self.probe_timeout_timer = None

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

    def _get_current_z_offset(self):
        """
        Get the current Z tool offset from the printer model.
        
        Returns:
            float: Current Z tool offset in millimeters, defaults to 0.0 if unavailable
        """
        try:
            if self.model and hasattr(self.model, 'tool_offsets'):
                current_z_offset = float(self.model.tool_offsets.get('Z', 0))
                self.logger.debug(f"Current Z offset from model: {current_z_offset}")
                return current_z_offset
            else:
                self.logger.warning("No printer model or tool_offsets available, using 0.0")
                return 0.0
        except (ValueError, AttributeError) as e:
            self.logger.warning(f"Error getting current Z offset: {e}, using 0.0")
            return 0.0

    # ==================== SIGNAL CONNECTION MANAGEMENT ====================

    def _connect_probe_tracking(self):
        """
        Connect probe tracking for receiving probe results.
        
        Establishes connection to the printer model's probe_accuracy_result_received
        signal for automated probe result processing. Ensures no duplicate connections.
        
        Raises:
            Exception: If probe tracking connection fails
        """
        if self._probe_tracking_connected:
            self.logger.debug("Probe tracking already connected - skipping")
            return
            
        if not self.model:
            self.logger.error("No model available for probe tracking connection")
            return
        
        try:
            self.model.probe_accuracy_result_received.connect(self.on_probe_result_received)
            self._probe_tracking_connected = True
            self.logger.info("Probe tracking connected successfully")
        except Exception as e:
            self.logger.error(f"Failed to connect probe tracking: {e}")
            self._probe_tracking_connected = False
            raise
    
    def _disconnect_probe_tracking(self):
        """
        Disconnect probe tracking when no longer needed.
        
        Safely disconnects from the printer model's probe result signals
        with proper error handling for various disconnect scenarios.
        Always resets connection flag regardless of success/failure.
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
