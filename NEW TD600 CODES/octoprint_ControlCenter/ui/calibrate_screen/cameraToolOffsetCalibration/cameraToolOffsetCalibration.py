"""
Camera Tool Offset Calibration Wizard
=====================================

Manual user-guided tool offset calibration using camera assistance and manual positioning.

Architecture:
- 7-step wizard: Clean Nozzles -> Connect Camera -> T0 Course -> T0 Fine -> T1 Course -> T1 Fine -> Results
- Manual positioning workflow with camera guidance and movement controls
- Timeout handling for robust position recording failure recovery
- Video demonstrations for user guidance on steps 1-2

Workflow:
1. Clean Nozzles - Heat both nozzles and position for cleaning (with instructional video)
2. Connect Camera - Position for camera and establish connection (with instructional video)
3. Position T0 Course - Manual positioning with coarse adjustment (0.5mm steps)
4. Position T0 Fine - Manual positioning with fine adjustment (0.02mm steps)
5. Position T1 Course - Manual positioning with coarse adjustment (0.5mm steps)
6. Position T1 Fine - Manual positioning with fine adjustment (0.02mm steps)
7. Results - Calculate and apply tool offsets with comprehensive validation

Features:
- Camera feed with crosshair overlay and zoom control for precise positioning
- Robust camera connection handling with retry/cancel options
- Position recording with timeout handling and user interaction options
- Quality offset calculation preserving existing values
- Comprehensive error handling and user feedback
- Instructional videos for critical steps

Dependencies:
- OpenCV for camera capture and image processing
- OctoPrint client for G-code commands and position tracking
- Printer model for position signals and current offset retrieval
- PyQt5 UI framework with custom dialog utilities
"""

import os
import sys
import time
import subprocess

# ==================== DYNAMIC OPENCV IMPORT AND INSTALLATION ====================

# Dynamic OpenCV import with automatic installation
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("OpenCV not found. Attempting to install...")
    
    try:
        # For Raspberry Pi - use prebuilt package to avoid long compilation
        print("Installing OpenCV using apt (prebuilt package)...")
        
        # Fix sources.list for older Raspberry Pi systems (Buster only)
        # This is required for OpenCV installation on older RPi models
        # Newer versions (Bullseye, Bookworm) don't need this
        try:
            # Check if running on Buster
            try:
                with open('/etc/os-release', 'r') as f:
                    os_info = f.read()
                is_buster = 'buster' in os_info.lower()
            except FileNotFoundError:
                # If can't read os-release, assume it might be needed
                is_buster = True
            
            if is_buster:
                print("Detected Buster - configuring apt sources for Raspberry Pi...")
                sources_line = "deb http://archive.raspberrypi.org/debian/ buster main"
                # Check if the line already exists, if not add it
                check_result = subprocess.run(['grep', '-Fxq', sources_line, '/etc/apt/sources.list'], 
                                             capture_output=True)
                if check_result.returncode != 0:
                    # Line doesn't exist, add it
                    subprocess.check_call(['sudo', 'tee', '-a', '/etc/apt/sources.list'], 
                                         input=f'\n{sources_line}\n'.encode(), 
                                         stdout=subprocess.DEVNULL)
                    print("✓ Raspberry Pi apt sources added to sources.list")
                else:
                    print("✓ Raspberry Pi apt sources already configured")
            else:
                print("Not running Buster - skipping sources.list modification")
        except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
            print(f"Warning: Could not update sources.list (may not be needed): {e}")
        
        subprocess.check_call(['sudo', 'apt', 'update'])
        subprocess.check_call(['sudo', 'apt', 'install', '-y', 'python3-opencv'])
        import cv2
        OPENCV_AVAILABLE = True
        print("✓ OpenCV installed successfully from apt!")
    except subprocess.CalledProcessError:
        # Fallback to pip if apt fails
        try:
            print("Apt installation failed, trying pip as fallback...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'opencv-python'])
            import cv2
            OPENCV_AVAILABLE = True
            print("✓ OpenCV installed successfully with pip!")
        except subprocess.CalledProcessError:
            # Final fallback with sudo pip
            try:
                subprocess.check_call(['sudo', 'pip3', 'install', 'opencv-python'])
                import cv2
                OPENCV_AVAILABLE = True
                print("✓ OpenCV installed successfully with sudo pip!")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"Failed to automatically install OpenCV: {e}")
                print("Please install it manually with: sudo apt install python3-opencv or pip install opencv-python")
                OPENCV_AVAILABLE = False

# ==================== PYQT5 AND UTILITY IMPORTS ====================

from PyQt5 import uic, QtCore, QtWidgets
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QLabel, QMessageBox
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QMutex
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QTransform, QMovie
from PyQt5.QtCore import Qt

from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import dialog

# ==================== CAMERA CAPTURE THREAD ====================


class CameraThread(QThread):
    """
    Camera Capture Thread
    ====================
    
    Handles camera capture operations in a separate thread to prevent UI blocking.
    Provides robust camera connection with segfault protection for Raspberry Pi environments.
    
    Features:
    - Safe camera initialization and cleanup
    - Zoom factor support for fine positioning
    - Frame buffering with mutex protection
    - Error handling and connection status reporting
    
    Signals:
    - changePixmap: Emitted when new frame is available
    - connectionError: Emitted when camera connection fails
    """
    
    changePixmap = pyqtSignal(QImage)
    connectionError = pyqtSignal(str)

    def __init__(self, camera_index=0):
        """
        Initialize camera thread.
        
        Args:
            camera_index (int): Camera device index (default: 0)
        """
        super().__init__()
        self.camera_index = camera_index
        self.running = False
        self.cap = None
        self.current_frame = None
        self.display_frame = None
        self._frame_lock = QtCore.QMutex()
        self.zoom_factor = 1.0

    def set_zoom(self, factor):
        """
        Set zoom factor for display.
        
        Args:
            factor (float): Zoom factor (1.0 = normal, 3.0 = 3x zoom)
        """
        self.zoom_factor = factor

    def try_connect(self):
        """Try to connect to USB camera with enhanced V4L2 support and segfault protection."""
        if not OPENCV_AVAILABLE:
            self.connectionError.emit("OpenCV not available")
            return False
            
        try:
            # Clean up any existing connection first
            if self.cap:
                try:
                    self.cap.release()
                except:
                    pass
                self.cap = None
                time.sleep(0.5)  # Give V4L2 more time for cleanup
            
            # Try to connect with V4L2 backend first for better Linux support
            try:
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)
                if not self.cap.isOpened():
                    # Fall back to default backend
                    self.cap = cv2.VideoCapture(self.camera_index)
            except (AttributeError, Exception):
                # OpenCV without V4L2 support or other error
                self.cap = cv2.VideoCapture(self.camera_index)
            
            if not self.cap.isOpened():
                self.connectionError.emit(f"USB camera {self.camera_index} not found or in use")
                return False
            
            # Give camera more time to initialize (important for V4L2)
            time.sleep(0.5)
            
            # Test reading a frame with safety checks
            for attempt in range(3):  # Try multiple times
                ret, frame = self.cap.read()
                if ret and frame is not None and frame.size > 0:
                    break
                time.sleep(0.2)  # Longer wait between attempts for V4L2
            else:
                self.cap.release()
                self.cap = None
                self.connectionError.emit(f"USB camera {self.camera_index} cannot capture frames")
                return False
                
            # Set basic camera properties safely - 10 FPS for stable operation
            try:
                self.cap.set(cv2.CAP_PROP_FPS, 10)
                
                # Disable autofocus if supported (helps prevent crashes)
                try:
                    self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
                except:
                    pass  # Ignore if autofocus control not supported
                
                # Set buffer size to 1 to reduce memory usage
                try:
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except:
                    pass  # Ignore if buffer size control not supported
                    
            except Exception as e:
                print(f"Warning: Could not set camera properties: {e}")
                # Continue anyway - properties are optional
            
            # Final test - try to read one more frame to ensure camera is stable
            try:
                ret, test_frame = self.cap.read()
                if ret and test_frame is not None and test_frame.size > 0:
                    height, width = test_frame.shape[:2]
                    print(f"Camera {self.camera_index} initialized successfully: {width}x{height}")
                    return True
                else:
                    self.cap.release()
                    self.cap = None
                    self.connectionError.emit(f"Camera {self.camera_index} cannot provide stable frames")
                    return False
            except Exception as e:
                self.cap.release()
                self.cap = None
                self.connectionError.emit(f"Camera {self.camera_index} final test failed: {e}")
                return False
                
        except Exception as e:
            if self.cap:
                try:
                    self.cap.release()
                except:
                    pass
                self.cap = None
            self.connectionError.emit(f"Camera connection error: {str(e)}")
            return False

    def run(self):
        """Main camera capture loop - segfault-safe for Raspberry Pi."""
        if not self.try_connect():
            return
            
        self.running = True
        frame_count = 0
        
        try:
            while self.running:
                # Extra safety check - ensure we're still supposed to be running
                if not self.running:
                    break
                    
                if self.cap and hasattr(self.cap, 'isOpened') and self.cap.isOpened():
                    try:
                        ret, frame = self.cap.read()
                        
                        # Check running flag again after potentially blocking read operation
                        if not self.running:
                            break
                            
                        if ret and frame is not None:
                            try:
                                # Basic safety checks for OpenCV 3.2.0 on Pi
                                if frame.size == 0 or not self.running:
                                    continue
                                    
                                with QtCore.QMutexLocker(self._frame_lock):
                                    # Check running flag inside mutex too
                                    if not self.running:
                                        break
                                        
                                    self.current_frame = frame.copy()
                                    
                                    # Apply zoom by cropping and resizing
                                    if self.zoom_factor > 1.0 and self.running:
                                        h, w = frame.shape[:2]
                                        if h > 0 and w > 0:  # Safety check
                                            center_x, center_y = w // 2, h // 2
                                            new_w, new_h = max(1, int(w / self.zoom_factor)), max(1, int(h / self.zoom_factor))
                                            x1 = max(0, center_x - new_w // 2)
                                            y1 = max(0, center_y - new_h // 2)
                                            x2 = min(w, x1 + new_w)
                                            y2 = min(h, y1 + new_h)
                                            
                                            if x2 > x1 and y2 > y1 and self.running:  # Ensure valid crop and still running
                                                cropped = frame[y1:y2, x1:x2]
                                                if cropped.size > 0:  # Safety check
                                                    frame = cv2.resize(cropped, (w, h))
                                    
                                    if self.running:  # Final check before storing
                                        self.display_frame = frame.copy()
                                
                                # Convert to QImage safely - only if still running
                                if self.running and frame.size > 0 and len(frame.shape) == 3:
                                    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                    h, w, ch = rgb_image.shape
                                    
                                    if h > 0 and w > 0 and ch > 0 and self.running:  # Safety checks
                                        bytes_per_line = ch * w
                                        # Make a copy to avoid memory issues
                                        rgb_copy = rgb_image.copy()
                                        qt_image = QImage(rgb_copy.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
                                        
                                        # Final check before emitting - prevent signals during shutdown
                                        if self.running and not self.signalsBlocked():
                                            self.changePixmap.emit(qt_image)
                            
                            except Exception as e:
                                # Don't emit errors for every frame to avoid spam
                                frame_count += 1
                                if frame_count % 30 == 0 and self.running:  # Log every 30 frames only, and only if still running
                                    print(f"Frame processing error: {e}")
                        
                    except Exception as e:
                        # Handle camera read errors
                        if self.running:  # Only log if we're supposed to be running
                            print(f"Camera read error: {e}")
                        break  # Exit loop on camera errors
                        
                    # Controlled frame rate with safety - check running flag before sleep
                    if self.running:
                        self.msleep(100)  # 10 FPS
                else:
                    # Camera not available - check if we should keep trying or exit
                    if self.running:
                        self.msleep(100)  # Longer wait if camera not available
                    else:
                        break  # Exit if not running
                    
        except Exception as e:
            # Only emit error if we're still supposed to be running (not during shutdown)
            if self.running and not self.signalsBlocked():
                try:
                    self.connectionError.emit(f"Camera thread error: {e}")
                except:
                    pass  # Ignore emit errors during shutdown
        finally:
            # Ensure complete cleanup even if there were errors
            self.running = False
            
            # Clear frame references to prevent memory access issues
            try:
                with QtCore.QMutexLocker(self._frame_lock):
                    self.current_frame = None
                    self.display_frame = None
            except:
                pass
            
            # Clean up camera resource with enhanced error handling
            if self.cap:
                try:
                    # Multiple cleanup attempts for maximum reliability
                    for attempt in range(3):
                        try:
                            if hasattr(self.cap, 'release') and callable(self.cap.release):
                                self.cap.release()
                            break
                        except Exception as cleanup_e:
                            if attempt == 2:  # Last attempt
                                print(f"Warning: Final camera cleanup attempt failed: {cleanup_e}")
                            else:
                                time.sleep(0.1)  # Brief pause before retry
                except:
                    pass  # Ignore all cleanup errors to prevent segfaults
                finally:
                    # Always set to None regardless of release success
                    self.cap = None
                    
            # Block any remaining signals to prevent callbacks after cleanup
            try:
                self.blockSignals(True)
            except:
                pass

    def stop(self):
        """Stop the camera thread safely with enhanced V4L2 resource management and segfault prevention."""
        # Set running flag to False first to stop the main loop
        self.running = False
        
        # Immediately disconnect from any signals to prevent callback issues
        try:
            self.blockSignals(True)
        except:
            pass
        
        # Clear any pending frames to prevent processing during shutdown
        try:
            with QtCore.QMutexLocker(self._frame_lock):
                self.current_frame = None
                self.display_frame = None
        except:
            pass
        
        # Stop any ongoing frame capture operations
        if self.cap and hasattr(self.cap, 'isOpened'):
            try:
                if self.cap.isOpened():
                    # Try to read one frame to clear buffer (helps with some cameras)
                    self.cap.read()
            except:
                pass  # Ignore any errors during buffer clearing
        
        # Give thread time to finish current operation gracefully
        if self.isRunning():
            # First try waiting normally
            if not self.wait(3000):  # Wait up to 3 seconds
                print("Warning: Camera thread did not stop cleanly, attempting forced termination...")
                try:
                    self.terminate()
                    # Give more time after termination
                    if not self.wait(2000):
                        print("Warning: Camera thread termination may not have completed properly")
                except:
                    print("Warning: Could not terminate camera thread cleanly")
        
        # Clean up camera resource safely with multiple attempts and enhanced error handling
        if self.cap:
            for attempt in range(5):  # Increased attempts for more robust cleanup
                try:
                    # Double-check if cap is still valid before releasing
                    if hasattr(self.cap, 'release') and callable(self.cap.release):
                        self.cap.release()
                    self.cap = None
                    break
                except Exception as e:
                    if attempt == 4:  # Last attempt
                        print(f"Warning: Camera cleanup error after {attempt + 1} attempts: {e}")
                        # Force set to None even if release failed to prevent further access
                        self.cap = None
                    else:
                        time.sleep(0.2)  # Longer pause between attempts
            
        # Ensure cap is None regardless of release success
        self.cap = None
            
        # Give system extra time to fully release camera resources and prevent segfaults
        # This is especially important for V4L2 and preventing resource conflicts
        try:
            time.sleep(0.8)  # Increased delay for more robust cleanup
        except:
            pass
        
        # Re-enable signals after cleanup
        try:
            self.blockSignals(False)
        except:
            pass


# ==================== MAIN CALIBRATION WIZARD CLASS ====================

class CameraToolOffsetCalibration(QWidget):
    """
    Camera Tool Offset Calibration Wizard
    =====================================
    
    Manual user-guided tool offset calibration using camera assistance and manual positioning.
    
    This wizard provides a comprehensive 7-step process:
    1. Clean Nozzles - Heat both nozzles and position for cleaning (with instructional video)
    2. Connect Camera - Position for camera and establish connection (with instructional video)
    3. Position T0 Course - Manual positioning with coarse adjustment (0.5mm steps)
    4. Position T0 Fine - Manual positioning with fine adjustment (0.02mm steps)
    5. Position T1 Course - Manual positioning with coarse adjustment (0.5mm steps)
    6. Position T1 Fine - Manual positioning with fine adjustment (0.02mm steps)
    7. Results - Calculate and apply tool offsets with comprehensive validation
    
    Key Features:
    - Camera feed with crosshair overlay and zoom control for precise positioning
    - Robust camera connection handling with retry/cancel options
    - Position recording with timeout handling and user interaction options
    - Quality offset calculation that preserves existing offset values
    - Comprehensive error handling with user-friendly feedback
    - Instructional videos for critical setup steps
    
    Architecture:
    - Uses MVP pattern with model signals for position tracking
    - Timeout-based error recovery for robust operation
    - Proper state management and cleanup on wizard exit
    - Video playback integration for user guidance
    """

    # ==================== CONSTANTS AND CONFIGURATION ====================
    
    # Step indices for clarity and maintainability
    STEP_CLEAN_NOZZLES = 0
    STEP_CONNECT_CAMERA = 1  
    STEP_POSITION_T0_COURSE = 2
    STEP_POSITION_T0_FINE = 3
    STEP_POSITION_T1_COURSE = 4
    STEP_POSITION_T1_FINE = 5
    STEP_RESULTS = 6
    TOTAL_STEPS = 7
    
    # Movement step sizes (mm)
    MOVEMENT_STEP_COARSE = 0.5
    MOVEMENT_STEP_FINE = 0.02
    
    # Camera zoom factors
    ZOOM_NORMAL = 1.0
    ZOOM_FINE = 3.0
    
    # Timeout configuration
    POSITION_TIMEOUT_SECONDS = 5
    
    # Removed VIDEO_SPECS - will be defined as instance variable for consistency

    # ==================== INITIALIZATION AND SETUP ====================

    def __init__(self, main_window):
        """
        Initialize the Camera Tool Offset Calibration Wizard.
        
        Sets up UI components, state variables, signal connections, and video resources
        for the manual tool offset calibration process.
        
        Args:
            main_window: Main application window providing access to printer model and OctoPrint client
        """
        super().__init__()
        self.main_window = main_window
        self.model = getattr(main_window, "printer_model", None)
        self.octoprint_client = getattr(main_window, "octoprint_client", None)
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing CameraToolOffsetCalibration")

        # Initialize state variables
        self._init_state_variables()
        
        # Load UI and initialize components
        self._load_ui()
        self._init_ui_components()
        self._connect_signals()
        
        # Initialize video resources
        self._init_video_resources()

        self.logger.info("CameraToolOffsetCalibration initialized successfully")

    def _init_state_variables(self):
        """
        Initialize all state tracking variables.
        
        Sets up camera state, positioning state, wizard navigation, position tracking,
        and video playback variables.
        """
        # Camera related attributes  
        self.camera_thread = None
        self.camera_available = False
        self.camera_setup_in_progress = False
        self.loading_dialog = None  # Dialog for camera loading
        
        # Positioning state
        self.tool0_position = None
        self.tool1_position = None
        self.current_tool = 0
        self.movement_step = self.MOVEMENT_STEP_COARSE  # Start with coarse movement
        
        # Wizard navigation state
        self._current_step = 0
        
        # Position tracking and timeout handling
        self._position_tracking_connected = False
        self.position_timeout_timer = None
        
        # Video playback state (unified system like NozzleChangeWizard)
        self.current_video_widget = None
        self.video_timer = None
        self.current_movie = None  # Currently playing QMovie object
        
        # Unified naming scheme to match NozzleChangeWizard
        self._video_movies = {}    # step_number -> QMovie mapping (same as _gif_movies pattern)
        
        # Video configuration (step_number, target_label_name, filename) - matches NozzleChangeWizard pattern
        self._video_specs = [
            (1, "step1Gif", "1_Nozzle Cleaning.gif"),      # Clean nozzles instruction video
            (2, "step2Gif", "2_Camera Placement.gif"),      # Camera connection instruction video
        ]

    def _load_ui(self):
        """
        Load the UI file with proper error handling.
        
        Raises:
            Exception: If UI file cannot be loaded
        """
        try:
            ui_file_path = os.path.join(os.path.dirname(__file__), "cameraToolOffsetCalibration.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("CameraToolOffsetCalibration UI loaded successfully")
        except Exception as e:
            self.logger.exception(f"Failed to load CameraToolOffsetCalibration UI file: {e}")
            raise

    def _init_ui_components(self):
        """
        Initialize and validate all UI components.
        
        Finds all required UI elements and validates their existence for robust operation.
        """
        # Main navigation components
        self.stackedWidget: QStackedWidget = self.findChild(QStackedWidget, "stackedWidget")
        self.stepLabel: QLabel = self.findChild(QLabel, "stepLabel")
        
        # Step pages
        self.step1Page: QWidget = self.findChild(QWidget, "step1Page")
        self.step2Page: QWidget = self.findChild(QWidget, "step2Page") 
        self.step3Page: QWidget = self.findChild(QWidget, "step3Page")
        self.resultStep: QWidget = self.findChild(QWidget, "resultStep")
        
        # Step 1 elements (Clean Nozzles)
        self.step1Label: QLabel = self.findChild(QLabel, "step1Label")
        self.step1Gif: QLabel = self.findChild(QLabel, "step1Gif")
        
        # Step 2 elements (Connect Camera)
        self.step2Label: QLabel = self.findChild(QLabel, "step2Label")
        self.step2Gif: QLabel = self.findChild(QLabel, "step2Gif")
        
        # Step 3 elements (Camera Feed)
        self.webCamFeed: QLabel = self.findChild(QLabel, "webCamFeed")
        
        # Results elements
        self.resultLabel: QLabel = self.findChild(QLabel, "resultLabel")
        
        # Movement buttons (matching UI names)
        self.moveXPButton: QPushButton = self.findChild(QPushButton, "moveXPButton")
        self.moveXMButton: QPushButton = self.findChild(QPushButton, "moveXMButton")
        self.moveYPButton: QPushButton = self.findChild(QPushButton, "moveYPButton")
        self.moveYMButton: QPushButton = self.findChild(QPushButton, "moveYMButton")
        self.moveZPButton: QPushButton = self.findChild(QPushButton, "moveZPButton")  
        self.moveZMButton: QPushButton = self.findChild(QPushButton, "moveZMButton")
        
        # Navigation buttons
        self.nextButton: QPushButton = self.findChild(QPushButton, "stepNextButton")
        self.cancelButton: QPushButton = self.findChild(QPushButton, "stepCancelButton")

        # Validate required elements
        required = [
            self.stackedWidget, self.stepLabel,
            self.step1Page, self.step2Page, self.step3Page, self.resultStep,
            self.step1Label, self.step2Label, self.webCamFeed, self.resultLabel,
            self.moveXPButton, self.moveXMButton, self.moveYPButton, self.moveYMButton,
            self.moveZPButton, self.moveZMButton,
            self.nextButton, self.cancelButton
        ]
        check_ui_elements(self, required, "CameraToolOffsetCalibration")

    def _connect_signals(self):
        """
        Connect all signal handlers.
        
        Sets up button connections and prepares for model signal connections.
        Note: Position tracking signals are connected only when needed for proper resource management.
        """
        # Navigation button connections
        self.nextButton.clicked.connect(self.on_next_clicked)
        self.cancelButton.clicked.connect(self.on_cancel_clicked)
        
        # Movement button connections - step size changes based on current step
        self.moveXPButton.clicked.connect(lambda: self.move_axis('X', self.movement_step))
        self.moveXMButton.clicked.connect(lambda: self.move_axis('X', -self.movement_step))
        self.moveYPButton.clicked.connect(lambda: self.move_axis('Y', self.movement_step))
        self.moveYMButton.clicked.connect(lambda: self.move_axis('Y', -self.movement_step))
        self.moveZPButton.clicked.connect(lambda: self.move_axis('Z', self.movement_step))
        self.moveZMButton.clicked.connect(lambda: self.move_axis('Z', -self.movement_step))

    def _init_video_resources(self):
        """Initialize video storage for lazy loading."""
        self._video_movies.clear()
        self.logger.info(f"Initialized video system with {len(self._video_specs)} video specifications")

    # ==================== VIDEO PLAYBACK MANAGEMENT ====================

    def _ensure_video_loaded(self, step_number):
        """
        Ensure video is loaded on-demand for the specified step (unified system).
        
        Uses the same configuration-driven approach as NozzleChangeWizard for consistency.
        
        Args:
            step_number (int): Step number to ensure video is loaded for
            
        Returns:
            QMovie: Loaded QMovie object if successful, None otherwise
        """
        if step_number in self._video_movies:
            return self._video_movies[step_number]  # Already loaded
            
        try:
            # Find the video spec for this step (unified approach)
            for spec_step_number, label_name, filename in self._video_specs:
                if spec_step_number == step_number:
                    video_dir = os.path.dirname(__file__)
                    video_path = os.path.join(video_dir, filename)
                    
                    if not os.path.exists(video_path):
                        self.logger.warning(f"Video file not found for step {step_number}: {video_path}")
                        return None
                    
                    # Create QMovie with unified configuration
                    movie = QMovie(video_path)
                    if not movie.isValid():
                        self.logger.warning(f"Video not valid for step {step_number}: {video_path}")
                        return None
                    
                    # Use CacheNone to avoid loading entire video into memory
                    movie.setCacheMode(QMovie.CacheNone)
                    
                    # Store in unified dictionary
                    self._video_movies[step_number] = movie
                    self.logger.info(f"Video loaded on-demand for step {step_number}: {filename}")
                    return movie
                    
        except Exception as e:
            self.logger.error(f"Error loading video for step {step_number}: {e}")
            
        return None

    def _find_video_label(self, step_number):
        """Find the label widget for a given step number."""
        for spec_step_number, label_name, _ in self._video_specs:
            if spec_step_number == step_number:
                return getattr(self, label_name, None)
        return None

    def _play_step_video(self, step_number):
        """Play instructional video for the specified step."""
        movie = self._ensure_video_loaded(step_number)
        if movie:
            label_widget = self._find_video_label(step_number)
            if label_widget:
                self._play_movie_in_label(movie, label_widget)

    # Removed redundant _play_page_video alias - use _play_step_video directly

    def _play_movie_in_label(self, movie, label_widget):
        """
        Play QMovie in the specified label widget.
        
        Args:
            movie (QMovie): QMovie object to play
            label_widget (QLabel): Label widget to display video in
        """
        try:
            # Validate inputs
            if not movie or not label_widget:
                self.logger.warning("Invalid movie or label widget provided")
                return
                
            # Stop any existing video
            self._stop_current_video()
            
            # Ensure movie is in stopped state before starting (fixes replay issues)
            if movie.state() != QMovie.NotRunning:
                movie.stop()
            
            # Jump to start of animation for proper replay
            movie.jumpToFrame(0)
            
            # Set up the movie in the label
            label_widget.setMovie(movie)
            self.current_movie = movie
            self.current_video_widget = label_widget
            
            # Start playing the movie
            movie.start()
            
            self.logger.info(f"Started playing video in {label_widget.objectName()}")
            
        except Exception as e:
            self.logger.error(f"Error playing movie in label: {e}")

    def _stop_current_video(self):
        """Stop currently playing video and clear references."""
        if self.current_movie:
            self.current_movie.stop()
            self.current_movie.jumpToFrame(0)
        if self.current_video_widget:
            self.current_video_widget.setMovie(None)
            self.current_video_widget.clear()
        if self.video_timer:
            self.video_timer.stop()
            self.video_timer = None
        self.current_movie = None
        self.current_video_widget = None





    def _release_video_resources(self):
        """Release all video resources from memory."""
        for movie in self._video_movies.values():
            movie.stop()
        self._video_movies.clear()



    # ==================== WIZARD LIFECYCLE AND NAVIGATION ====================
        self.logger.info("CameraToolOffsetCalibration initialized successfully")

    def showEvent(self, event):
        """
        Handle wizard activation - reset state and prepare UI.
        
        Called when the wizard widget becomes visible. Performs complete state
        reset including signal disconnections and data cleanup to ensure
        reliable operation across multiple wizard sessions.
        
        Args:
            event: Qt show event
        """
        super().showEvent(event)
        try:
            # Complete state reset including signal disconnections
            self._reset_wizard_state()
            self.logger.debug("🏠✨ Reset camera wizard state and UI on show")
        except Exception as e:
            self.logger.warning(f"⚠️ Error resetting wizard on show: {e}")

    def goto_step(self, index: int):
        """
        Navigate to the specified wizard step with proper setup and validation.
        
        Handles step bounds checking, UI page switching, video management,
        and step-specific initialization. Each step has its own setup method
        for clean separation of concerns.
        
        Args:
            index (int): Step index to navigate to (0-based, will be bounds-checked)
        """
        index = max(0, min(index, self.TOTAL_STEPS - 1))
        # Stop any currently playing video before switching steps
        self._stop_current_video()

        self._current_step = index
        if self.stackedWidget:
            # Map logical steps to UI pages
            if index == self.STEP_CLEAN_NOZZLES:
                page_index = 0  # step1Page
            elif index == self.STEP_CONNECT_CAMERA:
                page_index = 1  # step2Page
            elif index in [self.STEP_POSITION_T0_COURSE, self.STEP_POSITION_T0_FINE, 
                          self.STEP_POSITION_T1_COURSE, self.STEP_POSITION_T1_FINE]:
                page_index = 2  # step3Page (positioning page with camera and movement controls)
            elif index == self.STEP_RESULTS:
                page_index = 3  # resultStep
            else:
                page_index = 0  # fallback
                
            self.stackedWidget.setCurrentIndex(page_index)
        self._update_step_label()

        # Step-specific logic and video handling
        if index == self.STEP_CLEAN_NOZZLES:
            # Step 1: Clean Nozzles - Heat both nozzles in mirror mode
            self.nextButton.setText("Next")
            self.nextButton.setEnabled(True)
            self.step1Label.setText("Please clean both nozzle tips with a wire brush for best calibration results.\n\nBoth nozzles are heated to 80°C and positioned for easy cleaning.")
            self._start_nozzle_cleaning()
            self._play_step_video(1)  # Show cleaning video
            
        elif index == self.STEP_CONNECT_CAMERA:
            # Step 2: Connect Camera
            self.nextButton.setText("Next") 
            self.nextButton.setEnabled(True)
            self.step2Label.setText("Connect the USB calibration camera and place it exactly below the nozzle.\n\nThe printer is positioned at the center front for easy camera placement.")
            self._position_for_camera()
            self._play_step_video(2)  # Show camera connection video
            # Don't auto-start camera here - wait for user to click Next
            
        elif index in [self.STEP_POSITION_T0_COURSE, self.STEP_POSITION_T0_FINE, 
                       self.STEP_POSITION_T1_COURSE, self.STEP_POSITION_T1_FINE]:
            # Steps 3-6: Positioning steps
            # Release video resources since they're no longer needed after step 2
            if index == self.STEP_POSITION_T0_COURSE:  # Only do this on first positioning step
                self._release_video_resources()
                self.logger.debug("Released video resources - no longer needed after step 2")
            self._setup_positioning_step(index)
            
        elif index == self.STEP_RESULTS:
            # Step 7: Results
            self._show_results()

        self.logger.info(f"Switched to step {index + 1}/{self.TOTAL_STEPS}")

    def _update_step_label(self):
        """Update the step label."""
        try:
            if self.stepLabel:
                self.stepLabel.setText(f"Step {self._current_step + 1}/{self.TOTAL_STEPS}")
        except Exception:
            pass

    def _start_nozzle_cleaning(self):
        """Step 1: Heat both nozzles and position for cleaning."""
        if not self.octoprint_client:
            return
            
        try:
            # Home the printer
            self.octoprint_client.gcode("G28")

            # Set Z to 100mm
            self.octoprint_client.gcode("G1 Z100 F3000")
            
            # Set IDEX mode to Mirror
            self.octoprint_client.gcode("M605 S3")
            
            # Position at front of bed, X at 1/3 from left
            # Get machine build size from printer model
            build_size = getattr(self.model, 'machineBuildSize', {'X': 200}) if self.model else {'X': 200}
            bed_width = build_size.get('X', 200)
            x_position = int(bed_width / 3)  # 1/3 from left
            self.logger.info(f"Using bed width: {bed_width}mm, positioning at X{x_position} (1/3 from left)")
            self.octoprint_client.gcode(f"G1 X{x_position} Y20 F3000")
            
            # Heat both nozzles to 80C
            self.octoprint_client.gcode("M104 T0 S100")
            self.octoprint_client.gcode("M104 T1 S100")
            
            # Get latest M218 tool offsets from websockets
            self.octoprint_client.gcode("M503")
            
            self.logger.info("Nozzle cleaning setup complete")
            
        except Exception as e:
            self.logger.error(f"Error in nozzle cleaning setup: {e}")
            dialog.WarningOk(self, f"Error setting up nozzle cleaning: {e}")

    def _position_for_camera(self):
        """Step 2: Position for camera connection."""
        if not self.octoprint_client:
            return
            
        try:
            # Set regular mode and activate T0
            self.octoprint_client.gcode("M605 S1")
            self.octoprint_client.gcode("T0")
            
            # Move to center X, front Y, Z at 30mm
            # Get machine build size from printer model for center positioning
            build_size = getattr(self.model, 'machineBuildSize', {'X': 200}) if self.model else {'X': 200}
            bed_width = build_size.get('X', 200)
            x_center = int(bed_width / 2)  # Center of bed
            self.logger.info(f"Using bed width: {bed_width}mm, positioning camera at center X{x_center}")
            self.octoprint_client.gcode(f"G1 X{x_center} Y20 Z40 F3000")
            self.octoprint_client.gcode("M104 T0 S0")
            self.octoprint_client.gcode("M104 T1 S0")
            
            self.logger.info("Camera positioning setup complete")
            
        except Exception as e:
            self.logger.error(f"Error in camera positioning: {e}")
            dialog.WarningOk(self, f"Error positioning for camera: {e}")

    def _setup_positioning_step(self, step_index):
        """Setup positioning steps (3-6) with enhanced validation."""
        try:
            # Determine current tool and step type
            if step_index in [self.STEP_POSITION_T0_COURSE, self.STEP_POSITION_T0_FINE]:
                tool = 0
                tool_name = "T0"
            else:
                tool = 1 
                tool_name = "T1"
                
            is_fine = step_index in [self.STEP_POSITION_T0_FINE, self.STEP_POSITION_T1_FINE]
            
            # Validate prerequisites for T1 steps
            if tool == 1 and not hasattr(self, 'tool0_position'):
                self.logger.error("T1 positioning attempted without T0 position recorded")
                dialog.WarningOk(self, "T0 position must be recorded before T1 positioning. Please restart the calibration.")
                self.goto_step(self.STEP_CLEAN_NOZZLES)
                return
            
            # Set movement step resolution
            self.movement_step = 0.02 if is_fine else 0.5
            
            # Setup camera if not already running
            if not (hasattr(self, 'camera_thread') and self.camera_thread and self.camera_thread.isRunning()):
                # Start camera with loading dialog
                self.start_camera_with_loading_dialog()
            else:
                # Camera already running, update zoom configuration
                self._configure_camera_for_step(is_fine)
            
            # Update UI for current step
            step_type = "Fine" if is_fine else "Course"
            self.nextButton.setText("Record Position" if is_fine else "Fine Positioning")
            
            self.logger.info(f"Setup {step_type} positioning for {tool_name}")
            
        except Exception as e:
            self.logger.error(f"Error setting up positioning step: {e}")
            dialog.WarningOk(self, f"Error setting up positioning: {e}")


    def on_cancel_clicked(self):
        """Handle cancel button clicks and return to main calibrate screen."""
        try:
            self.logger.info("Camera wizard cancel clicked - performing cleanup")
            
            # Comprehensive cleanup to prevent segfaults
            self.cleanup()
            
            # Additional safety cleanup (stop_camera is now part of cleanup, but being extra safe)
            try:
                self.stop_camera()
            except Exception as e:
                self.logger.warning(f"Additional camera stop error (non-critical): {e}")
            
            # Turn off heaters for safety
            if hasattr(self, 'octoprint_client') and self.octoprint_client:
                try:
                    self.octoprint_client.gcode("M104 T0 S0")
                    self.octoprint_client.gcode("M104 T1 S0")
                except Exception as e:
                    self.logger.warning(f"Error turning off heaters (non-critical): {e}")
            
            # Return to main calibrate screen (similar to NozzleChangeWizard pattern)
            self.main_window.calibrate_screen.show_calibrate_screen()
                        
        except Exception as e:
            self.logger.error(f"Error in cancel handler: {e}")
            # Even if there's an error, ensure some cleanup and try to return to calibrate screen
            try:
                # Force cleanup attempt even if main cleanup failed
                self._stop_camera_resources()
            except:
                pass
            # Always try to return to calibrate screen
            try:
                self.main_window.calibrate_screen.show_calibrate_screen()
            except Exception as return_e:
                self.logger.error(f"Critical error: Could not return to calibrate screen: {return_e}")

    def on_next_clicked(self):
        """Handle next button clicks with proper validation and error handling."""
        try:
            current_step = self._current_step
            
            if current_step == self.STEP_CLEAN_NOZZLES:
                # Move to camera connection step
                self.goto_step(self.STEP_CONNECT_CAMERA)
                
            elif current_step == self.STEP_CONNECT_CAMERA:
                # Show loading dialog and try to connect camera
                try:
                    self.start_camera_with_loading_dialog()
                except Exception as e:
                    self.logger.error(f"Error starting camera connection: {e}")
                    # Use unified camera error handling
                    self._handle_camera_error_with_retry(f"Connection error: {str(e)}")
                return  # Don't proceed to next step until camera is handled
                
            elif current_step == self.STEP_POSITION_T0_COURSE:
                # Validate camera is available before proceeding
                if not self.camera_available:
                    dialog.WarningOk(self, "Camera is not available. Please ensure camera is connected and working.")
                    return
                # Move to T0 fine positioning
                self.goto_step(self.STEP_POSITION_T0_FINE)
                
            elif current_step == self.STEP_POSITION_T0_FINE:
                # Record T0 position and wait for position update to proceed to T1 setup
                try:
                    self._record_tool_position(0)
                    # Don't call goto_step here - let on_position_updated handle it
                    # to avoid timing issues with M114 response
                except Exception as e:
                    self.logger.error(f"Error recording T0 position: {e}")
                    dialog.WarningOk(self, f"Error recording T0 position: {e}")
                
            elif current_step == self.STEP_POSITION_T1_COURSE:
                # Validate T0 was recorded before proceeding
                if not hasattr(self, 'tool0_position') or self.tool0_position is None:
                    dialog.WarningOk(self, "T0 position not recorded. Please go back and complete T0 positioning.")
                    return
                # Move to T1 fine positioning
                self.goto_step(self.STEP_POSITION_T1_FINE)
                
            elif current_step == self.STEP_POSITION_T1_FINE:
                # Record T1 position and wait for position update to proceed to results
                try:
                    self._record_tool_position(1)
                    # Don't call goto_step here - let on_position_updated handle it
                    # to avoid timing issues with M114 response
                except Exception as e:
                    self.logger.error(f"Error recording T1 position: {e}")
                    dialog.WarningOk(self, f"Error recording T1 position: {e}")
                
            elif current_step == self.STEP_RESULTS:
                # Validate both positions are recorded before applying offsets
                if not hasattr(self, 'tool0_position') or self.tool0_position is None:
                    dialog.WarningOk(self, "T0 position not recorded. Please complete the calibration process.")
                    return
                if not hasattr(self, 'tool1_position') or self.tool1_position is None:
                    dialog.WarningOk(self, "T1 position not recorded. Please complete the calibration process.")
                    return
                # Apply tool offsets and finish
                try:
                    self._apply_tool_offsets()
                except Exception as e:
                    self.logger.error(f"Error applying tool offsets: {e}")
                    dialog.WarningOk(self, f"Error applying tool offsets: {e}")
                
        except Exception as e:
            self.logger.error(f"Error in next button handler: {e}")
            dialog.WarningOk(self, f"An error occurred: {e}")

    # ========================================================================================
    # SECTION 4: CAMERA HANDLING
    # ========================================================================================
    # Functions for camera initialization, connection management, error handling,
    # and video feed processing. Includes retry logic for connection failures.

    def _configure_camera_for_step(self, is_fine):
        """Configure camera zoom for the current step."""
        try:
            if hasattr(self, 'camera_thread') and self.camera_thread:
                # Set zoom factor: 3x for fine positioning, 1x for course
                zoom = 3.0 if is_fine else 1.0
                self.camera_thread.set_zoom(zoom)
                self.logger.info(f"Set camera zoom to {zoom}x for {'fine' if is_fine else 'course'} positioning")
        except Exception as e:
            self.logger.error(f"Error configuring camera: {e}")

    def _on_camera_connection_failed(self):
        """Handle failed camera connection with retry dialog."""
        try:
            self.camera_setup_in_progress = False
            
            # Hide loading dialog if it exists
            self.hide_loading_dialog()
            
            # Show retry dialog using RetryCancel
            result = dialog.RetryCancel(
                parent=self,
                text="Camera Connection Failed\n\nNo camera detected.\nPlease check camera connection.\n\nRetry or cancel?",
                overlay=True,
                icon="warning"
            )
            
            if result == "retry":
                # User wants to retry - attempt connection again with small delay
                self.logger.info("User chose to retry camera connection")
                QTimer.singleShot(500, self.start_camera_with_loading_dialog)
            else:
                # User cancelled - cleanup and exit the wizard entirely
                self.logger.info("User cancelled camera setup")
                self.cleanup()
                self.on_cancel_clicked()  # Exit the wizard
                
        except Exception as e:
            self.logger.error(f"Error handling camera connection failure: {e}")
            # Fallback - cleanup and exit wizard on error
            self.cleanup()
            self.on_cancel_clicked()

    def start_camera_with_loading_dialog(self):
        """Show loading dialog and start camera initialization."""
        if self.camera_setup_in_progress:
            return  # Prevent multiple simultaneous attempts
        
        self.camera_setup_in_progress = True
        
        try:
            # Show loading dialog
            self.show_loading_dialog()
            
            # Use a timer to start camera after dialog is shown
            QTimer.singleShot(100, self.start_camera)
            
        except Exception as e:
            self.logger.error(f"Error starting camera with loading: {e}")
            self.hide_loading_dialog()
            self.show_camera_error(f"Initialization error: {str(e)}")

    def show_loading_dialog(self):
        """Show 'Please wait, loading...' dialog."""
        try:
            self.loading_dialog = dialog.dialog(
                self, 
                "Please wait, loading camera...", 
                buttons=QMessageBox.NoButton,  # No buttons
                overlay=True,
                icon=":/Icons/img/icons/information.png"
            )
            self.loading_dialog.show()
            self.logger.info("Loading dialog shown")
        except Exception as e:
            self.logger.error(f"Error showing loading dialog: {e}")

    def hide_loading_dialog(self):
        """Hide the loading dialog."""
        try:
            if self.loading_dialog:
                self.loading_dialog.hide()
                self.loading_dialog = None
                self.logger.info("Loading dialog hidden")
        except Exception as e:
            self.logger.error(f"Error hiding loading dialog: {e}")

    def start_camera(self):
        """Initialize and start the camera feed."""
        if not OPENCV_AVAILABLE:
            self.hide_loading_dialog()
            self.show_camera_error("OpenCV not available - install opencv-python")
            return
            
        try:
            self.logger.info("Starting camera feed...")
            
            # Try to find an available camera
            camera_index = self.find_available_camera()
            
            if camera_index is not None:
                self.camera_thread = CameraThread(camera_index)
                self.camera_thread.changePixmap.connect(self._update_camera_feed)
                self.camera_thread.connectionError.connect(self._on_camera_error)
                self.camera_thread.start()
                self.camera_available = True
                self.camera_setup_in_progress = False
                self.logger.info(f"Camera started successfully on index {camera_index}")
                
                # Hide loading dialog on success
                self.hide_loading_dialog()
                
                # Configure initial zoom (start with 1x)
                self.camera_thread.set_zoom(1.0)
                
                # Camera ready - proceed to positioning step
                self.goto_step(self.STEP_POSITION_T0_COURSE)
            else:
                self.hide_loading_dialog()
                self.camera_setup_in_progress = False
                self._on_camera_connection_failed()
                
        except Exception as e:
            self.logger.error(f"Error starting camera: {e}")
            self.hide_loading_dialog()
            self.camera_setup_in_progress = False
            self._on_camera_connection_failed()

    def find_available_camera(self):
        """Find the first available USB camera index using v4l2-ctl to detect USB devices."""
        if not OPENCV_AVAILABLE:
            return None
        
        import cv2
        import time
        
        # Force cleanup any existing camera resources first
        self._ensure_camera_cleanup_before_search()
        
        # First try using v4l2-ctl to intelligently detect USB camera
        usb_camera_index = self._find_usb_camera_with_v4l2()
        if usb_camera_index is not None:
            self.logger.info(f"Found USB camera at index {usb_camera_index} using v4l2-ctl")
            # Verify it works with OpenCV
            if self._test_camera_index(usb_camera_index):
                return usb_camera_index
            else:
                self.logger.warning(f"USB camera at index {usb_camera_index} detected by v4l2-ctl but failed OpenCV test")
        
        # Fallback: Check indices 1-5 first (USB cameras typically start at 1 if CSI is at 0)
        self.logger.info("Falling back to sequential camera index search")
        for i in range(1, 6):
            if self._test_camera_index(i):
                return i
        
        # If no cameras found at 1+, check index 0 but assume it might be CSI
        if self._test_camera_index(0):
            return 0
            
        return None

    def _find_usb_camera_with_v4l2(self):
        """
        Use v4l2-ctl to find USB camera device and return its index.
        
        Returns:
            int or None: Camera index if USB camera found, None otherwise
        """
        try:
            import subprocess
            import re
            
            # Run v4l2-ctl --list-devices to get device information
            result = subprocess.run(
                ['v4l2-ctl', '--list-devices'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                self.logger.warning(f"v4l2-ctl command failed with return code {result.returncode}")
                return None
            
            output = result.stdout
            self.logger.debug(f"v4l2-ctl output:\n{output}")
            
            # Parse output to find USB camera
            # Look for lines containing "usb-" which indicates USB device
            # Example: "HD Camera: HD Camera (usb-fe980000.usb-1.1):"
            lines = output.split('\n')
            usb_device_section = False
            video_devices = []
            
            for line in lines:
                # Check if this line indicates a USB device
                if 'usb-' in line.lower():
                    usb_device_section = True
                    video_devices = []  # Reset for new device section
                    self.logger.debug(f"Found USB device section: {line}")
                # Check if we hit a new device section (not USB)
                elif line and not line.startswith('\t') and not line.startswith(' '):
                    # New device section started
                    if usb_device_section and video_devices:
                        # We were in USB section and found devices, use the first one
                        break
                    usb_device_section = False
                    video_devices = []
                # If in USB device section, collect video device paths
                elif usb_device_section and line.strip().startswith('/dev/video'):
                    device_path = line.strip()
                    video_devices.append(device_path)
                    self.logger.debug(f"Found video device in USB section: {device_path}")
            
            # Extract camera index from the first USB video device
            if video_devices:
                first_device = video_devices[0]
                # Extract number from /dev/videoN
                match = re.search(r'/dev/video(\d+)', first_device)
                if match:
                    camera_index = int(match.group(1))
                    self.logger.info(f"Detected USB camera at /dev/video{camera_index}")
                    return camera_index
            
            self.logger.warning("No USB camera found in v4l2-ctl output")
            return None
            
        except subprocess.TimeoutExpired:
            self.logger.warning("v4l2-ctl command timed out")
            return None
        except FileNotFoundError:
            self.logger.warning("v4l2-ctl command not found - install v4l-utils package")
            return None
        except Exception as e:
            self.logger.error(f"Error running v4l2-ctl to find USB camera: {e}")
            return None

    def _ensure_camera_cleanup_before_search(self):
        """Ensure any existing camera resources are fully cleaned up before searching."""
        try:
            # Stop any existing camera thread
            if hasattr(self, 'camera_thread') and self.camera_thread:
                self.logger.info("Cleaning up existing camera thread before search")
                self.camera_thread.stop()
                if self.camera_thread.isRunning():
                    self.camera_thread.wait(2000)  # Wait up to 2 seconds
                self.camera_thread = None
                
            # Reset state
            self.camera_available = False
            self.camera_setup_in_progress = False
            
            # Give extra time for V4L2 resources to be fully released
            import time
            time.sleep(0.5)
            
        except Exception as e:
            self.logger.warning(f"Error during camera cleanup before search: {e}")

    def _test_camera_index(self, index):
        """Test if a camera at the given index is accessible with enhanced V4L2 handling."""
        try:
            import cv2
            import time
            
            self.logger.debug(f"Testing camera index {index}")
            
            # For V4L2 cameras, try to open with CAP_V4L2 backend if available
            cap = None
            try:
                cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
            except (AttributeError, Exception):
                cap = cv2.VideoCapture(index)
            
            if not cap.isOpened():
                self.logger.debug(f"Camera index {index} failed to open")
                if cap:
                    cap.release()
                return False
            
            # Give camera more time to initialize (important for V4L2)
            time.sleep(0.5)
            
            success_count = 0
            
            # Try multiple reads to test stability
            for attempt in range(3):
                try:
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        # Check if frame has valid dimensions
                        if hasattr(frame, 'shape') and len(frame.shape) >= 2:
                            height, width = frame.shape[:2]
                            if height > 0 and width > 0:
                                success_count += 1
                                self.logger.debug(f"Camera index {index} read success {success_count}/3")
                                break  # One successful read is enough
                except Exception as e:
                    self.logger.debug(f"Camera index {index} read attempt {attempt + 1} failed: {e}")
                
                time.sleep(0.1)
            
            # Proper cleanup with more time for V4L2
            try:
                cap.release()
            except Exception as e:
                self.logger.debug(f"Error releasing camera {index}: {e}")
            
            # Give V4L2 more time to release the resource
            time.sleep(0.5)
            
            is_working = success_count > 0
            self.logger.debug(f"Camera index {index} test result: {'working' if is_working else 'not working'}")
            return is_working
                
        except Exception as e:
            self.logger.debug(f"Exception testing camera index {index}: {e}")
            try:
                if 'cap' in locals() and cap:
                    cap.release()
                    time.sleep(0.3)  # Extra time after exception
            except:
                pass
            return False

    def _update_camera_feed(self, qt_image):
        """Update the camera feed with crosshair overlay."""
        if not self.webCamFeed:
            return
            
        # Create pixmap from image
        pixmap = QPixmap.fromImage(qt_image)
        
        # Mirror the image horizontally (flip left-right)
        mirrored_pixmap = pixmap.transformed(QTransform().scale(-1, 1))
        
        # Draw crosshair overlay on the mirrored image
        painter = QPainter(mirrored_pixmap)
        painter.setPen(QPen(Qt.red, 3))  # Thicker pen for better visibility
        
        # Draw bigger circle and crosshair in center - double the size
        center_x = mirrored_pixmap.width() // 2
        center_y = mirrored_pixmap.height() // 2
        radius = 60 if self.movement_step == 0.02 else 40  # Double the radius (was 30/20)
        
        # Draw circle
        painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)
        
        # Draw longer crosshair lines - double the length
        cross_length = radius + 30  # Double the cross length (was radius + 15)
        painter.drawLine(center_x - cross_length, center_y, center_x + cross_length, center_y)
        painter.drawLine(center_x, center_y - cross_length, center_x, center_y + cross_length)
        
        painter.end()
        
        # Scale to fit the label while maintaining aspect ratio
        label_size = self.webCamFeed.size()
        scaled_pixmap = mirrored_pixmap.scaled(
            label_size.width(), label_size.height(),
            QtCore.Qt.KeepAspectRatio, 
            QtCore.Qt.SmoothTransformation
        )
        
        # Update the label
        self.webCamFeed.setPixmap(scaled_pixmap)

    def _on_camera_error(self, error_msg):
        """Handle camera connection errors - unified error handling."""
        try:
            self.logger.error(f"Camera error: {error_msg}")
            
            # Stop camera thread safely
            if hasattr(self, 'camera_thread') and self.camera_thread:
                try:
                    self.camera_thread.stop()
                    self.camera_thread.wait(1000)  # Wait up to 1 second
                except:
                    pass
                self.camera_thread = None
            
            # Close any loading dialog
            self.hide_loading_dialog()
            
            # Reset setup flag
            self.camera_setup_in_progress = False
            
            # Show retry dialog using consistent pattern
            self._handle_camera_error_with_retry(error_msg)
            
        except Exception as e:
            self.logger.error(f"Error in camera error handler: {e}")
            # Fallback - reset state and cleanup
            self.camera_setup_in_progress = False
            self.camera_available = False
            self.cleanup()
            self.on_cancel_clicked()
    
    def _handle_camera_error_with_retry(self, error_msg):
        """Show camera error dialog with retry/cancel options."""
        try:
            # Format the error message for better display
            formatted_msg = f"Camera Error\n\n{error_msg}\n\nRetry or cancel the calibration?"
            
            # Use RetryCancel from utils.dialog for consistent styling
            result = dialog.RetryCancel(
                parent=self,
                text=formatted_msg,
                overlay=True,
                icon="warning"
            )
            
            if result == "retry":
                self.logger.info("User chose to retry after camera error")
                QTimer.singleShot(500, self.start_camera_with_loading_dialog)
            else:
                self.logger.info("User cancelled after camera error")
                # Cancel - cleanup and exit the wizard entirely
                self.cleanup()
                self.on_cancel_clicked()  # Exit the wizard
                
        except Exception as e:
            self.logger.error(f"Error showing camera error dialog: {e}")
            # Fallback - cleanup and exit wizard on error
            self.cleanup()
            self.on_cancel_clicked()
    
    def _connect_position_tracking(self):
        """Connect position tracking when needed for recording tool positions."""
        if self._position_tracking_connected:
            self.logger.debug("Position tracking already connected - skipping")
            return
            
        if not self.model:
            self.logger.error("No printer model available for position tracking")
            return
            
        try:
            self.model.current_position_updated.connect(self.on_position_updated)
            self._position_tracking_connected = True
            self.logger.debug("Position tracking connected")
        except Exception as e:
            self.logger.error(f"Failed to connect position tracking: {e}")
            raise
    
    def _disconnect_position_tracking(self):
        """Disconnect position tracking when no longer needed."""
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
            self.logger.debug("Position tracking disconnected")
        except (TypeError, AttributeError) as e:
            self._position_tracking_connected = False
            self.logger.debug(f"Position tracking was already disconnected: {e}")
        except Exception as e:
            self.logger.error(f"Error disconnecting position tracking: {e}")
            self._position_tracking_connected = False

    # ========================================================================================
    # SECTION 5: POSITIONING AND MOVEMENT CONTROL
    # ========================================================================================
    # Functions for nozzle positioning, movement control, position recording,
    # and coordinate system management for tool offset calculations.

    def move_axis(self, axis, distance):
        """Move the specified axis by the given distance"""
        if not self.octoprint_client:
            self.logger.warning("No OctoPrint client available for movement")
            return
            
        try:    
            command = f"G91\nG1 {axis}{distance} F3000\nG90"
            self.octoprint_client.gcode(command)
            self.logger.debug(f"Moving {axis} by {distance}mm")
        except Exception as e:
            self.logger.error(f"Error moving {axis} axis: {e}")
            dialog.WarningOk(self, f"Error moving {axis} axis: {e}")

    def _record_tool_position(self, tool):
        """Record the current position for the specified tool with validation."""
        if not self.octoprint_client:
            self.logger.error("No OctoPrint client available for position recording")
            dialog.WarningOk(self, "No printer connection available")
            return
            
        # Validate tool number
        if tool not in [0, 1]:
            self.logger.error(f"Invalid tool number: {tool}")
            return
            
        # Validate we're in a fine positioning step
        if (tool == 0 and self._current_step != self.STEP_POSITION_T0_FINE) or \
           (tool == 1 and self._current_step != self.STEP_POSITION_T1_FINE):
            self.logger.warning(f"Position recording for tool {tool} attempted in wrong step: {self._current_step}")
            return
            
        try:
            # Disconnect any existing position tracking before connecting new one
            self._disconnect_position_tracking()
            
            # Connect position tracking for this recording
            self._connect_position_tracking()
            
            # Send M114 to get current position
            self.current_tool = tool
            self.octoprint_client.gcode("M114")
            self.logger.info(f"Requesting position for tool {tool}")
            
            # Set up a timeout in case position update doesn't come through
            if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
                self.position_timeout_timer.stop()
                self.logger.debug("Stopped existing position timeout timer")
            
            self.position_timeout_timer = QTimer()
            self.position_timeout_timer.setSingleShot(True)
            self.position_timeout_timer.timeout.connect(lambda: self._handle_position_timeout(tool))
            self.position_timeout_timer.start(self.POSITION_TIMEOUT_SECONDS * 1000)  # Convert to milliseconds
            self.logger.info(f"Started position timeout timer for tool {tool} ({self.POSITION_TIMEOUT_SECONDS} seconds)")
            
        except Exception as e:
            self.logger.error(f"Error recording tool {tool} position: {e}")
            dialog.WarningOk(self, f"Error recording position: {e}")

    def _handle_position_timeout(self, tool):
        """Handle position recording timeout - simplified approach."""
        try:
            # Check if we already have position for this tool (timeout may be stale)
            if ((tool == 0 and self.tool0_position is not None) or
                (tool == 1 and self.tool1_position is not None)):
                self.logger.debug(f"Position timeout triggered but already have position for tool {tool} - ignoring")
                return
                
            self.logger.warning(f"Position recording timeout for tool {tool}")
            
            # Disconnect position tracking to prevent further signals
            self._disconnect_position_tracking()
            
            # Clean up timeout timer
            if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
                self.position_timeout_timer.stop()
                self.position_timeout_timer = None
            
            # Show dialog asking user what to do with more concise text
            result = dialog.RetryCancel(
                parent=self,
                text=f"Position Recording Timeout\n\nNo response from Tool {tool}.\n\nRetry or cancel the calibration?",
                overlay=True,
                icon="warning"
            )
            
            if result == "retry":
                # Retry position recording
                self.logger.info(f"User chose to retry position recording for tool {tool}")
                # Reset state before retrying
                self.current_tool = None
                QTimer.singleShot(500, lambda: self._record_tool_position(tool))
            else:
                # Cancel - cleanup and exit the wizard entirely
                self.logger.info(f"User cancelled position recording for tool {tool}")
                self._reset_position_recording_state()
                self.cleanup()
                self.on_cancel_clicked()  # Exit the wizard
                
        except Exception as e:
            self.logger.error(f"Error handling position timeout: {e}")
            # Reset state on error and exit wizard
            self._reset_position_recording_state()
            self.cleanup()
            self.on_cancel_clicked()  # Exit the wizard on error too

    def _reset_position_recording_state(self):
        """Reset position recording state variables."""
        try:
            self.current_tool = None
            self._disconnect_position_tracking()
            
            # Clean up timeout timer with proper null checking
            if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
                self.position_timeout_timer.stop()
                self.position_timeout_timer = None
                
        except Exception as e:
            self.logger.error(f"Error resetting position recording state: {e}")

    def on_position_updated(self, position):
        """Handle position updates from websocket. Simplified approach using current_tool only."""
        try:
            # Only process if we have a current tool and are in FINE positioning steps (where position recording happens)
            fine_positioning_steps = [self.STEP_POSITION_T0_FINE, self.STEP_POSITION_T1_FINE]
            
            if (self.current_tool is None or 
                self._current_step not in fine_positioning_steps or
                'x' not in position or 'y' not in position):
                self.logger.debug(f"Ignoring position update - current_tool={self.current_tool}, step={self._current_step}, fine_steps={fine_positioning_steps}")
                return
                
            # Check if we already have position for this tool
            if ((self.current_tool == 0 and self.tool0_position is not None) or
                (self.current_tool == 1 and self.tool1_position is not None)):
                self.logger.debug(f"Ignoring position update - already have position for tool {self.current_tool}")
                return
                
            pos = {'x': position['x'], 'y': position['y']}
            self.logger.info(f"Processing position update for tool {self.current_tool}: {pos}")
            
            # Cancel timeout timer since we got a position update
            if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
                self.position_timeout_timer.stop()
                self.position_timeout_timer = None
                self.logger.debug("Position timeout timer stopped successfully")
                
            if self.current_tool == 0:
                self.tool0_position = pos
                self.logger.info(f"Recorded T0 position: {pos}")
            elif self.current_tool == 1:
                self.tool1_position = pos
                self.logger.info(f"Recorded T1 position: {pos}")
                
            # Proceed to next step after position is recorded
            if self.current_tool == 0:  # T0 position recorded, switch to T1 and go to T1 course
                def proceed_to_t1():
                    self.octoprint_client.gcode("T1")
                    self.logger.info("Switched to tool 1")
                    # Move T1 to where T0 was positioned before switching tools
                    if hasattr(self, 'tool0_position'):
                        t0_x = self.tool0_position['x']
                        t0_y = self.tool0_position['y']
                        self.octoprint_client.gcode(f"G1 X{t0_x} Y{t0_y} F3000")
                        self.logger.info(f"Moved T1 to T0's recorded position: X{t0_x}, Y{t0_y}")
                    self.goto_step(self.STEP_POSITION_T1_COURSE)
                QTimer.singleShot(100, proceed_to_t1)
            elif self.current_tool == 1:  # T1 position recorded, go to results
                QTimer.singleShot(100, lambda: self.goto_step(self.STEP_RESULTS))
                    
                # Reset current tool
                self.current_tool = None
                
                # Disconnect position tracking since we got what we needed
                self._disconnect_position_tracking()
                
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}")

    # ========================================================================================
    # SECTION 6: RESULTS AND CALCULATIONS
    # ========================================================================================
    # Functions for displaying calibration results, calculating tool offsets,
    # and applying the final offset values to the printer configuration.

    def _show_results(self):
        """Show the results and calculated offsets."""
        try:
            self.nextButton.setText("Apply Tool Offsets")
            
            # Debug logging to see what positions we have
            self.logger.info(f"Checking positions - T0: {getattr(self, 'tool0_position', None)}, T1: {getattr(self, 'tool1_position', None)}")
            
            # More explicit check for positions
            t0_pos = getattr(self, 'tool0_position', None)
            t1_pos = getattr(self, 'tool1_position', None)
            
            if t0_pos is not None and t1_pos is not None and isinstance(t0_pos, dict) and isinstance(t1_pos, dict):
                # Get current tool offsets from printer model for display only
                current_x_offset = float(getattr(self.model, 'tool_offsets', {}).get('X', 0)) if self.model else 0.0
                current_y_offset = float(getattr(self.model, 'tool_offsets', {}).get('Y', 0)) if self.model else 0.0
                
                # Use direct position differences without trying to remove current offsets
                # Both T0 and T1 positions from M114 should be treated as logical positions
                # For SET_GCODE_OFFSET: offset is ADDED to gcode coordinate to get mechanical position
                # So if T1 is 5mm right of T0, we need +5mm offset so T1 moves to correct mechanical position
                raw_x_diff = t1_pos['x'] - t0_pos['x']  # T1 - T0: if T1 is right of T0, this is positive
                raw_y_diff = t1_pos['y'] - t0_pos['y']  # T1 - T0: if T1 is above T0, this is positive
                
                self.logger.info(f"Position differences (T1-T0) - X: {round(raw_x_diff, 3)}, Y: {round(raw_y_diff, 3)}")
                
                # The offset should be the difference directly (SET_GCODE_OFFSET adds this to gcode coords)
                new_x_offset = round(current_x_offset + raw_x_diff, 3)
                new_y_offset = round(current_y_offset + raw_y_diff, 3)

                # Store calculated offsets
                self.calculated_offsets = {
                    'x': new_x_offset,
                    'y': new_y_offset
                }
                
                self.logger.info(f"Calculated tool offsets - X: {new_x_offset}, Y: {new_y_offset}")
                
                # Display results in UI
                results_text = f"""Calibration Complete!
Position Differences (T1-T0):
• X Difference: {raw_x_diff:.3f}mm
• Y Difference: {raw_y_diff:.3f}mm
New Tool Offsets (will be applied):
• X Offset: {new_x_offset:.3f}mm
• Y Offset: {new_y_offset:.3f}mm
Click "Apply Tool Offsets" to save these settings."""
                
                self._display_results_text(results_text)
                
            else:
                self.logger.error(f"Missing position data - T0: {t0_pos}, T1: {t1_pos}")
                error_text = f"""Calibration Error

Missing position data for offset calculation.

T0 Position: {t0_pos if t0_pos else 'Not recorded'}
T1 Position: {t1_pos if t1_pos else 'Not recorded'}

Please restart the calibration process."""
                
                self._display_results_text(error_text)
                
        except Exception as e:
            self.logger.error(f"Error showing results: {e}")
            error_text = f"Error calculating results: {e}"
            self._display_results_text(error_text)

    def _display_results_text(self, text):
        """Display results text in the resultLabel."""
        self.resultLabel.setText(text)
        self.resultLabel.show()
        self.logger.info("Displaying results in resultLabel")

    def _apply_tool_offsets(self):
        """Apply the calculated tool offsets."""
        if not self.octoprint_client:
            dialog.WarningOk(self, "No printer connection available")
            return
            
        if not hasattr(self, 'calculated_offsets'):
            dialog.WarningOk(self, "No calculated offsets available. Please complete the calibration process first.")
            return
            
        try:
            x_offset = round(self.calculated_offsets['x'], 3)
            y_offset = round(self.calculated_offsets['y'], 3)
            
            # Apply tool offsets using M218
            self.octoprint_client.gcode(f"M218 T1 X{x_offset} Y{y_offset}")
            
            # Save configuration using M500 (standard EEPROM save command)
            self.octoprint_client.gcode("M500")
            
            self.logger.info(f"Applied tool offsets - X: {x_offset}, Y: {y_offset}")
            
            dialog.InfoOk(self, f"Tool offsets applied successfully!\nX: {x_offset:.3f}mm\nY: {y_offset:.3f}mm")
            
            # Ensure complete cleanup before finishing
            self.cleanup()
            
            # Return to main calibrate screen
            self.main_window.calibrate_screen.show_calibrate_screen()
            
        except Exception as e:
            self.logger.error(f"Error applying tool offsets: {e}")
            dialog.WarningOk(self, f"Error applying tool offsets: {e}")

    # ========================================================================================
    # SECTION 7: STATE MANAGEMENT AND CLEANUP
    # ========================================================================================
    # Functions for wizard state management, resource cleanup, and lifecycle management.

    def _reset_wizard_state(self):
        """
        Reset all wizard state variables to initial values.
        
        Performs complete state cleanup including signal disconnections,
        step reset, and data clearing. This is called when the wizard
        is opened to ensure clean starting state.
        
        ⚠️  DO NOT call this when exiting/canceling - use cleanup() instead!
        """
        try:
            # Core resource cleanup (shared with cleanup)
            self._cleanup_core_resources()
            
            # Reset to first step (only for wizard restart, not exit!)
            self.goto_step(self.STEP_CLEAN_NOZZLES)
            
            # Reset wizard-specific state variables
            self._reset_state_variables()
                
            self.logger.debug("🔄✨ Camera wizard state reset complete")
            
        except Exception as e:
            self.logger.error(f"Error resetting wizard state: {e}")

    def cleanup(self):
        """
        Cleanup resources WITHOUT restarting the wizard.
        
        Use this when canceling, exiting, or handling errors where
        you want to clean up but NOT restart the wizard.
        """
        try:
            # Core resource cleanup only - no goto_step call
            self._cleanup_core_resources()
            
            # Release video resources from memory when exiting
            self._release_video_resources()
            
            # Reset state variables only - no wizard restart
            self._reset_state_variables()
                
            self.logger.debug("🧹 Camera wizard cleanup complete (no restart)")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

    def _reset_state_variables(self):
        """Reset all state variables to initial values."""
        self.tool0_position = None
        self.tool1_position = None
        self.current_tool = 0
        self.movement_step = self.MOVEMENT_STEP_COARSE
        self._current_step = 0

    def _cleanup_core_resources(self):
        """
        Cleanup core resources (cameras, signals, timers, videos).
        
        This is the shared cleanup logic used by both _reset_wizard_state()
        and cleanup() to avoid code duplication.
        """
        # Disconnect all tracking
        self._disconnect_position_tracking()
        
        # Stop any video playback
        self._stop_current_video()
        
        # Stop camera
        self._stop_camera_resources()
        
        # Clean up timeout timer with proper null checking
        if hasattr(self, 'position_timeout_timer') and self.position_timeout_timer:
            self.position_timeout_timer.stop()
            self.position_timeout_timer = None

    def _stop_camera_resources(self):
        """Stop camera and clean up camera-related resources with enhanced V4L2 handling and segfault prevention."""
        # Hide loading dialog if it's still showing
        self.hide_loading_dialog()
        
        # Clear camera feed display immediately to prevent accessing freed memory
        try:
            if hasattr(self, 'webCamFeed') and self.webCamFeed:
                self.webCamFeed.clear()
                self.webCamFeed.setText("Camera stopped")
        except:
            pass
        
        if hasattr(self, 'camera_thread') and self.camera_thread:
            self.logger.debug("Stopping camera thread with enhanced cleanup...")
            
            # Disconnect ALL signals to prevent any callbacks during shutdown
            try:
                self.camera_thread.changePixmap.disconnect()
                self.camera_thread.connectionError.disconnect()
            except:
                pass  # Signals might already be disconnected
            
            # Block any new signals from the thread
            try:
                self.camera_thread.blockSignals(True)
            except:
                pass
            
            # Check if thread is running before attempting to stop
            if self.camera_thread.isRunning():
                # Stop the thread with enhanced error handling
                try:
                    self.camera_thread.stop()
                    
                    # Wait for thread to actually stop with multiple attempts
                    max_wait_attempts = 3
                    for attempt in range(max_wait_attempts):
                        if not self.camera_thread.isRunning():
                            break
                        wait_time = (attempt + 1) * 1000  # 1s, 2s, 3s
                        if not self.camera_thread.wait(wait_time):
                            self.logger.warning(f"Camera thread did not stop after {wait_time}ms (attempt {attempt + 1}/{max_wait_attempts})")
                            if attempt == max_wait_attempts - 1:
                                # Last attempt - force termination
                                try:
                                    self.logger.warning("Forcing camera thread termination")
                                    self.camera_thread.terminate()
                                    self.camera_thread.wait(2000)
                                except Exception as e:
                                    self.logger.error(f"Error during forced camera thread termination: {e}")
                        else:
                            self.logger.debug(f"Camera thread stopped successfully on attempt {attempt + 1}")
                            break
                            
                except Exception as e:
                    self.logger.error(f"Error during camera thread shutdown: {e}")
                    # Even if there's an error, continue with cleanup
            
            # Clear the reference and reset state
            try:
                # Delete the thread object to free memory
                del self.camera_thread
            except:
                pass
            self.camera_thread = None
            self.camera_available = False
        
        # Reset all camera-related flags
        self.camera_setup_in_progress = False
        
        # Give system significant time to fully release camera resources and prevent segfaults
        # This is critical for V4L2 cameras and preventing resource conflicts
        try:
            import time
            self.logger.debug("Waiting for camera resources to be fully released...")
            time.sleep(1.0)  # Increased delay for maximum stability
        except:
            pass
        
        self.logger.debug("Camera resources cleanup completed")

    # ========================================================================================
    # SECTION 8: UTILITY AND LIFECYCLE METHODS
    # ========================================================================================
    # Functions for camera utilities and widget lifecycle management.

    def stop_camera(self):
        """Stop the camera feed safely - public interface."""
        try:
            self._stop_camera_resources()
            self.logger.info("Camera stopped successfully")
        except Exception as e:
            self.logger.error(f"Error stopping camera: {e}")
            # Even if there's an error, ensure state is reset
            self.camera_thread = None
            self.camera_available = False
            self.camera_setup_in_progress = False

    def closeEvent(self, event):
        """Handle widget close event with comprehensive cleanup to prevent segfaults."""
        try:
            self.logger.info("Camera wizard closeEvent triggered - performing comprehensive cleanup")
            
            # Perform comprehensive cleanup first
            self.cleanup()
            
            # Additional safety measures for closeEvent
            try:
                # Ensure all timers are stopped
                for child in self.findChildren(QTimer):
                    if child and child.isActive():
                        child.stop()
                        
                # Clear any remaining video resources
                if hasattr(self, 'webCamFeed') and self.webCamFeed:
                    self.webCamFeed.clear()
                    
                # Permanently destroy QMovie objects only on final close
                if hasattr(self, 'step1_movie') and self.step1_movie:
                    self.step1_movie.stop()
                    self.step1_movie = None
                if hasattr(self, 'step2_movie') and self.step2_movie:
                    self.step2_movie.stop()
                    self.step2_movie = None
                    
                # Turn off heaters as safety measure
                if hasattr(self, 'octoprint_client') and self.octoprint_client:
                    try:
                        self.octoprint_client.gcode("M104 T0 S0")
                        self.octoprint_client.gcode("M104 T1 S0")
                    except:
                        pass  # Non-critical if this fails
                        
            except Exception as cleanup_e:
                self.logger.warning(f"Additional cleanup error (non-critical): {cleanup_e}")
            
            # Give extra time for all resources to be fully released
            try:
                import time
                time.sleep(0.2)  # Brief additional delay for complete resource release
            except:
                pass
                
            super().closeEvent(event)
            self.logger.info("Camera wizard closeEvent completed successfully")
            
        except Exception as e:
            # Even if cleanup fails, always call parent closeEvent to prevent hanging
            self.logger.error(f"Close event error: {e}")
            try:
                super().closeEvent(event)
            except:
                pass  # Prevent any exceptions from blocking widget closure
