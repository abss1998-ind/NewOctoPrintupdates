"""
Change Filament Wizard
======================

Overview
--------
This widget orchestrates the user flow for changing filament on the printer.
It manages UI state transitions, temperature ramping, and printer motion/extrusion
commands for both loading and unloading operations.

Pages and flow
--------------
1. changeFilamentPage (landing)
    - User chooses Load or Unload and selects a material (or "Loaded Filament").

2. changeFilamentProgressPage (heating)
    - Shows heating progress for the active tool. When target reached,
      it automatically transitions to the next phase based on operation:
         - Load: changeFilamentLoadPage
         - Unload: changeFilamentRetractPage (after a small priming extrude)

3. changeFilamentLoadPage (load assist)
    - Continuously extrudes slowly to pull filament into the extruder.
    - User can proceed to the next page to extrude to the nozzle tip.

4. changeFilamentExtrudePage (advance to nozzle tip)
    - Extrudes in larger steps until filament reaches the hotend and purges.

5. changeFilamentRetractPage (unload assist)
    - Performs tip shaping and retracts filament back through Bowden/PTFE.

Inactivity timeout
------------------
An inactivity timer cancels the wizard after 5 minutes of no user input
while on any of the active extrude/retract pages. Any mouse, keyboard, or touch
activity resets the timer. On timeout, the wizard cancels and returns to the
main filament management screen.

Notes
-----
- Public method names and signal connections are preserved.
- Async loops exit when the current page changes, so leaving a page
  or cancelling stops motion commands safely.
"""

import os
import time
from PyQt5 import uic, QtCore
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QComboBox, QProgressBar, QLabel
from utils.helpers import check_ui_elements, run_async
from utils.logger import get_logger
from utils.printer_ui_config import is_dual_nozzle_printer, force_single_tool
from utils import dialog

# UI/logic constants
LOADED_FILAMENT_LABEL = "Loaded Filament"
TPU_MATERIAL_NAME = "TPU"

# Compatibility for PyQt5 string conversion
try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

logger = get_logger(__name__)


class ChangeFilamentWizard(QWidget):
    """Wizard widget to guide the user through loading or unloading filament.

    Responsibilities:
    - Manage page navigation and wire UI signals.
    - Coordinate heating and printer G-code commands.
    - Provide async helper loops for pull-in, extrusion to nozzle, and retraction.
    - Enforce a 5-minute inactivity timeout on action pages.
    """
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.model = main_window.printer_model
        self.octoprint_client = main_window.octoprint_client
        self.changeFilamentHeatingFlag = False
        self.loadFlag = None
        self.activeExtruder = 0  # Default to extruder 0

        # Inactivity timer (5 minutes) to auto-cancel during async operations
        self.INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000
        self._inactivity_timer = QtCore.QTimer(self)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.timeout.connect(self._on_inactivity_timeout)

        # Use centralized logger
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing ChangeFilament widget")

        # Load UI
        try:
            ui_file_path = os.path.join(os.path.dirname(__file__), "changeFilamentWizard.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("changeFilamentWizard UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load changeFilamentWizard UI file: {e}", exc_info=True)
            return

        # Initialize UI components
        self.stackedWidget = self.findChild(QStackedWidget, "stackedWidget")
        self.changeFilamentPage = self.findChild(QWidget, "changeFilamentPage")
        self.changeFilamentProgressPage = self.findChild(QWidget, "changeFilamentProgressPage")
        self.changeFilamentLoadPage = self.findChild(QWidget, "changeFilamentLoadPage")
        self.changeFilamentExtrudePage = self.findChild(QWidget, "changeFilamentExtrudePage")
        self.changeFilamentRetractPage = self.findChild(QWidget, "changeFilamentRetractPage")
        self.changeFilamentBackButton = self.findChild(QPushButton, "changeFilamentBackButton")
        self.changeFilamentBackButton2 = self.findChild(QPushButton, "changeFilamentBackButton2")
        self.changeFilamentBackButton3 = self.findChild(QPushButton, "changeFilamentBackButton3")
        self.changeFilamentLoadButton = self.findChild(QPushButton, "changeFilamentLoadButton")
        self.changeFilamentUnloadButton = self.findChild(QPushButton, "changeFilamentUnloadButton")
        self.loadedTillExtruderButton = self.findChild(QPushButton, "loadedTillExtruderButton")
        self.loadDoneButton = self.findChild(QPushButton, "loadDoneButton")
        self.unloadDoneButton = self.findChild(QPushButton, "unloadDoneButton")
        self.changeFilamentComboBox = self.findChild(QComboBox, "changeFilamentComboBox")
        self.changeFilamentProgress = self.findChild(QProgressBar, "changeFilamentProgress")
        self.changeFilamentStatus = self.findChild(QLabel, "changeFilamentStatus")
        self.changeFilamentNameOperation = self.findChild(QLabel, "changeFilamentNameOperation")

        # Validate UI components
        components = [
            self.stackedWidget, self.changeFilamentPage, self.changeFilamentProgressPage,
            self.changeFilamentLoadPage, self.changeFilamentExtrudePage, self.changeFilamentRetractPage,
            self.changeFilamentBackButton, self.changeFilamentBackButton2, self.changeFilamentBackButton3,
            self.changeFilamentLoadButton, self.changeFilamentUnloadButton,
            self.loadedTillExtruderButton, self.loadDoneButton, self.unloadDoneButton,
            self.changeFilamentComboBox, self.changeFilamentProgress, self.changeFilamentStatus
        ]
        check_ui_elements(self, components, "ChangeFilament")


        # UI button connections
        self.changeFilamentBackButton.clicked.connect(self.changeFilamentCancel)
        self.changeFilamentBackButton2.clicked.connect(self.changeFilamentCancel)
        self.changeFilamentBackButton3.clicked.connect(self.changeFilamentCancel)
        self.changeFilamentLoadButton.clicked.connect(self.loadFilament)
        self.changeFilamentUnloadButton.clicked.connect(self.unloadFilament)
        self.loadedTillExtruderButton.clicked.connect(self.changeFilamentExtrudePageFunction)
        self.loadDoneButton.clicked.connect(self.changeFilamentDone)
        self.unloadDoneButton.clicked.connect(self.changeFilamentDone)

        self.stackedWidget.setCurrentWidget(self.changeFilamentPage)
        self.setActiveExtruder(0)

        # Install event filters on this widget and its children to track user activity
        self._install_inactivity_event_filters()


	# Redundantly called buy setup(), so commenting out
    # def showEvent(self, event):
    #     """On show, reset to landing page to ensure a known state."""
    #     super().showEvent(event)
    #     try:
    #         self.changeFilament()
    #         self.logger.debug("Reset stacked widget to changeFilamentPage on show")
    #     except Exception as e:
    #         self.logger.error(f"Error resetting to changeFilamentPage: {e}")

    def changeFilament(self):
        """Initialize landing page and populate material options.   

        Resets operation flags, homes if safe, selects the active tool,
        and prepares the material selection list.
        """
        logger.info("ChangeFilament.changeFilament() started")
        # None means no operation yet; set True on load, False on unload
        self.loadFlag = None
        self.changeFilamentHeatingFlag = False
        try:
            self.stackedWidget.setCurrentWidget(self.changeFilamentPage)
            time.sleep(1)
            if self.model.printer_status not in ["Printing", "Paused"]:
                self.octoprint_client.gcode("G28")
            elif self.model.printer_status == "Printing":
                self.octoprint_client.pausePrint()
            self.selectToolChangeFilament()
            self.stackedWidget.setCurrentWidget(self.changeFilamentPage)
            self.changeFilamentComboBox.clear()
            self.changeFilamentComboBox.addItems(self.model.filaments.keys())
            tool0TargetTemperature = self.model.temperatures.get('tool0Target', None)
            if tool0TargetTemperature and self.model.printer_status in ["Printing", "Paused"]:
                self.changeFilamentComboBox.addItem(LOADED_FILAMENT_LABEL)
                index = self.changeFilamentComboBox.findText(LOADED_FILAMENT_LABEL)
                if index >= 0:
                    self.changeFilamentComboBox.setCurrentIndex(index)
        except Exception as e:
            logger.error(f"Error in ChangeFilament.changeFilament: {e}")
            dialog.WarningOk(self, f"Error in ChangeFilament.changeFilament: {e}", overlay=True)

    def selectToolChangeFilament(self):
        """Select the tool (T0/T1) for the current active extruder and jog to purge position."""
        logger.info("changeFilament.selectToolChangeFilament started")
        try:
            # Use the activeExtruder value (set by setup() or model signal) to select tool and jog
            if not is_dual_nozzle_printer():
                # Force tool0 for single nozzle
                self.octoprint_client.selectTool(0)
                self.octoprint_client.jog(self.model.tool0PurgePosition['X'], self.model.tool0PurgePosition["Y"], absolute=True, speed=10000)
            elif int(self.activeExtruder) == 1:
                self.octoprint_client.selectTool(1)
                self.octoprint_client.jog(self.model.tool1PurgePosition['X'], self.model.tool1PurgePosition["Y"], absolute=True, speed=10000)
            else:
                self.octoprint_client.selectTool(0)
                self.octoprint_client.jog(self.model.tool0PurgePosition['X'], self.model.tool0PurgePosition["Y"], absolute=True, speed=10000)
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error in changeFilament.selectToolChangeFilament: {e}")
            dialog.WarningOk(self, f"Error in changeFilament.selectToolChangeFilament: {e}", overlay=True)

    def changeFilamentCancel(self):
        """Cancel the wizard, stop timers/signals, cool down (if idle), and return to main screen."""
        logger.info("ChangeFilament.changeFilamentCancel started")
        try:
            self._stop_inactivity_timer()
            self._disconnect_temperature_signal()
            if self.model.printer_status not in ["Printing", "Paused"]:
                self.main_window.control_screen.coolDownAction()
            self.main_window.filament_management_screen.show_material_nozzle_screen()     
            self.stackedWidget.setCurrentWidget(self.changeFilamentPage)
            self.loadFlag = None
            self.changeFilamentHeatingFlag = False
        except Exception as e:
            logger.error(f"Error in ChangeFilament.changeFilamentCancel: {e}")
            dialog.WarningOk(self, f"Error in ChangeFilament.changeFilamentCancel: {e}", overlay=True)

    def loadFilament(self):
        """Begin Load flow: jog to purge position, set temp (if material selected), and heat."""
        logger.info("changeFilament.loadFilament started - Updated one")
        try:
            self._jog_to_purge_position()
            self.logger.debug("Jogging to purge position done")
            if self.changeFilamentComboBox.findText(LOADED_FILAMENT_LABEL) == -1:
                self._set_tool_temperature()
            self.stackedWidget.setCurrentWidget(self.changeFilamentProgressPage)
            self.model.temperatures_updated.connect(self.updateTemperature)
            self.changeFilamentStatus.setText(f"Heating Tool {self.activeExtruder}, Please Wait...")
            self.changeFilamentNameOperation.setText(f"Loading {self.changeFilamentComboBox.currentText()}")
            self.changeFilamentHeatingFlag = True
            self.loadFlag = True
        except Exception as e:
            # On error, ensure no persistence happens if user taps Done
            self.loadFlag = None
            self.changeFilamentHeatingFlag = False
            logger.error(f"Error in changeFilament.loadFilament: {e}")
            dialog.WarningOk(self, f"Error in changeFilament.loadFilament: {e}", overlay=True)

    def unloadFilament(self):
        """Begin Unload flow: jog to purge position, set temp (if material selected), and heat."""
        logger.info("changeFilament.unloadFilament started")
        try:
            self._jog_to_purge_position()
            if self.changeFilamentComboBox.findText(LOADED_FILAMENT_LABEL) == -1:
                self._set_tool_temperature()
            self.stackedWidget.setCurrentWidget(self.changeFilamentProgressPage)
            self.model.temperatures_updated.connect(self.updateTemperature)
            self.changeFilamentStatus.setText(f"Heating Tool {self.activeExtruder}, Please Wait...")
            self.changeFilamentNameOperation.setText(f"Unloading {self.changeFilamentComboBox.currentText()}")
            self.changeFilamentHeatingFlag = True
            self.loadFlag = False
        except Exception as e:
            # On error, ensure no persistence happens if user taps Done
            self.loadFlag = None
            self.changeFilamentHeatingFlag = False
            logger.error(f"Error in changeFilament.unloadFilament: {e}")
            dialog.WarningOk(self, f"Error in changeFilament.unloadFilament: {e}", overlay=True)

    def _disconnect_temperature_signal(self):
        """Safely disconnect the temperature update signal if connected."""
        try:
            self.model.temperatures_updated.disconnect(self.updateTemperature)
        except TypeError:
            # Signal was not connected, which is fine
            pass

    def _install_inactivity_event_filters(self):
        """Install event filters on this widget and all children to detect user input.

        Any relevant user interaction (mouse/keyboard/touch) resets the inactivity timer
        while it's active.
        """
        try:
            # Install on self
            self.installEventFilter(self)
            # And on all current children
            for obj in self.findChildren(QtCore.QObject):
                obj.installEventFilter(self)
        except Exception as e:
            self.logger.warning(f"Failed to install event filters for inactivity tracking: {e}")

    def eventFilter(self, obj, event):
        """Reset inactivity timer when active and user interacts with the wizard."""
        try:
            if self._inactivity_timer.isActive():
                et = event.type()
                if et in (
                    QtCore.QEvent.MouseButtonPress,
                    QtCore.QEvent.MouseButtonRelease,
                    QtCore.QEvent.MouseMove,
                    QtCore.QEvent.Wheel,
                    QtCore.QEvent.KeyPress,
                    QtCore.QEvent.KeyRelease,
                    QtCore.QEvent.TouchBegin,
                    QtCore.QEvent.TouchUpdate,
                    QtCore.QEvent.TouchEnd,
                ):
                    self._reset_inactivity_timer()
        except Exception:
            # Don't let the event filter break normal UI flow
            pass
        return super().eventFilter(obj, event)

    def _start_inactivity_timer(self):
        """Start the inactivity timer (runs on UI thread)."""
        try:
            # Ensure this runs on the UI thread
            QtCore.QTimer.singleShot(0, lambda: self._inactivity_timer.start(self.INACTIVITY_TIMEOUT_MS))
            self.logger.debug("Inactivity timer start requested")
        except Exception as e:
            self.logger.warning(f"Failed to start inactivity timer: {e}")

    def _reset_inactivity_timer(self):
        """Reset the inactivity timer if it is currently running."""
        try:
            if self._inactivity_timer.isActive():
                QtCore.QTimer.singleShot(0, lambda: self._inactivity_timer.start(self.INACTIVITY_TIMEOUT_MS))
        except Exception:
            pass

    def _stop_inactivity_timer(self):
        """Stop the inactivity timer if it is running (thread-safe)."""
        try:
            if self._inactivity_timer.isActive():
                QtCore.QTimer.singleShot(0, lambda: self._inactivity_timer.stop())
                self.logger.debug("Inactivity timer stop requested")
        except Exception:
            pass

    def _on_inactivity_timeout(self):
        """Auto-cancel the wizard and return to the main filament management screen."""
        try:
            self.logger.info("Inactivity timeout reached; auto-cancelling filament change wizard")
            # This will also switch away from the async pages, causing their loops to exit
            self.changeFilamentCancel()
        except Exception as e:
            self.logger.error(f"Error handling inactivity timeout: {e}")

    def updateTemperature(self, temp):
        """Update heating progress and advance to load/retract stage when ready."""
        try:
            if not self.changeFilamentHeatingFlag:
                return
            extruder = self.activeExtruder
            tool_target = temp.get(f'tool{extruder}Target', 0)
            tool_actual = temp.get(f'tool{extruder}Actual', 0)
            if tool_target == 0:
                self.changeFilamentProgress.setMaximum(300)
            elif tool_target - tool_actual > 1:
                self.changeFilamentProgress.setMaximum(tool_target)
            else:
                self.changeFilamentProgress.setMaximum(tool_actual)
                self.changeFilamentHeatingFlag = False
                self._disconnect_temperature_signal()
                if self.loadFlag:
                    self.changeFilamentLoadFunction()
                else:
                    self.octoprint_client.extrude(5)
                    self.changeFilamentRetractFunction()
            self.changeFilamentProgress.setValue(tool_actual)
        except Exception as e:
            logger.error(f"Error in changeFilament.updateTemperature: {e}")
            dialog.WarningOk(self, f"Error in changeFilament.updateTemperature: {e}", overlay=True)

    @run_async
    def changeFilamentLoadFunction(self):
        """After heating (Load): gently pull filament into the extruder in short steps."""
        logger.info("ChangeFilament.changeFilamentLoadFunction started")
        try:
            self.stackedWidget.setCurrentWidget(self.changeFilamentLoadPage)
            self._start_inactivity_timer()
            while self.stackedWidget.currentWidget() == self.changeFilamentLoadPage:
                self.octoprint_client.gcode("G91")
                self.octoprint_client.gcode("G1 E5 F100")
                self.octoprint_client.gcode("G90")
                time.sleep(self.calcExtrudeTime(5, 100))
        except Exception as e:
            logger.error(f"Error in ChangeFilament.changeFilamentLoadFunction: {e}")
            dialog.WarningOk(self, f"Error in ChangeFilament.changeFilamentLoadFunction: {e}", overlay=True)
        finally:
            self._stop_inactivity_timer()

    @run_async
    def changeFilamentExtrudePageFunction(self, *args, **kwargs):
        """After loading, extrude until filament reaches nozzle and purges reliably."""
        logger.info("ChangeFilament.changeFilamentExtrudePageFunction started")
        try:
            self.logger.debug("Entered extrusion loop to reach nozzle")
            self.stackedWidget.setCurrentWidget(self.changeFilamentExtrudePage)
            self._start_inactivity_timer()
            for i in range(int(self.model.ptfeTubeLength / 150)):
                self.octoprint_client.gcode("G91")
                self.octoprint_client.gcode("G1 E150 F1500")
                self.octoprint_client.gcode("G90")
                time.sleep(self.calcExtrudeTime(150, 1500))
                if self.stackedWidget.currentWidget() is not self.changeFilamentExtrudePage:
                    self.logger.debug("Extrude page left; stopping initial extrusion steps")
                    break
            self.logger.debug("Initial extrusion steps done; entering continuous purge loop")
            while self.stackedWidget.currentWidget() == self.changeFilamentExtrudePage:
                feed = 200 if self.changeFilamentComboBox.currentText() == TPU_MATERIAL_NAME else 400
                self.octoprint_client.gcode("G91")
                self.octoprint_client.gcode(f"G1 E20 F{feed}")
                self.octoprint_client.gcode("G90")
                time.sleep(self.calcExtrudeTime(20, feed))
            self.logger.debug("Extrude page loop exited")
        except Exception as e:
            logger.error(f"Error in ChangeFilament.changeFilamentExtrudePageFunction: {e}")
            dialog.WarningOk(self, f"Error in ChangeFilament.changeFilamentExtrudePageFunction: {e}", overlay=True)
        finally:
            self._stop_inactivity_timer()

    @run_async
    def changeFilamentRetractFunction(self):
        """After heating (Unload): tip-shape and retract filament through the tube."""
        logger.info("ChangeFilament.changeFilamentRetractFunction started")
        try:
            self.logger.debug("Entered retraction loop")
            self.stackedWidget.setCurrentWidget(self.changeFilamentRetractPage)
            self._start_inactivity_timer()
            feed = 300 if self.changeFilamentComboBox.currentText() == TPU_MATERIAL_NAME else 600
            self.octoprint_client.gcode("G91")
            self.octoprint_client.gcode(f"G1 E10 F{feed}")
            time.sleep(self.calcExtrudeTime(10, feed))
            self.octoprint_client.gcode("G1 E-25 F6000")
            time.sleep(self.calcExtrudeTime(20, 6000))
            time.sleep(8)  # wait for filament to cool inside the nozzle
            self.octoprint_client.gcode("G1 E-150 F5000")
            time.sleep(self.calcExtrudeTime(150, 5000))
            self.octoprint_client.gcode("G90")
            for _ in range(int(self.model.ptfeTubeLength / 150)):
                self.octoprint_client.gcode("G91")
                self.octoprint_client.gcode("G1 E-150 F2000")
                self.octoprint_client.gcode("G90")
                time.sleep(self.calcExtrudeTime(150, 2000))
                if self.stackedWidget.currentWidget() is not self.changeFilamentRetractPage:
                    self.logger.debug("Retract page left; stopping tube retraction steps")
                    break
            while self.stackedWidget.currentWidget() == self.changeFilamentRetractPage:
                self.octoprint_client.gcode("G91")
                self.octoprint_client.gcode("G1 E-5 F1000")
                self.octoprint_client.gcode("G90")
                time.sleep(self.calcExtrudeTime(5, 1000))
            self.logger.debug("Retract page loop exited")
        except Exception as e:
            logger.error(f"Error in ChangeFilament.changeFilamentRetractFunction: {e}")
            dialog.WarningOk(self, f"Error in ChangeFilament.changeFilamentRetractFunction: {e}", overlay=True)
        finally:
            self._stop_inactivity_timer()

    def calcExtrudeTime(self, length, speed):
        """Compute seconds required to extrude 'length' mm at 'speed' mm/min."""
        return length / (speed / 60)

    def setActiveExtruder(self, activeNozzle):
        """Update current active extruder index (slot hooked to model signal)."""
        logger.info("changeFilament.setActiveExtruder started")
        try:
            activeNozzle = int(activeNozzle)
            # UI toggle removed; just store activeExtruder
            self.activeExtruder = activeNozzle
        except Exception as e:
            logger.error(f"Error in changeFilament.setActiveExtruder: {e}")
            dialog.WarningOk(self, f"Error in changeFilament.setActiveExtruder: {e}", overlay=True)

    # New setup API so filamentManagementScreen can pass which tool/bay opened the wizard
    def setup(self, params=None):
        """Prepare and open the wizard for a specific tool if provided.

        Params can be:
            - dict with 'tool': e.g. {"tool": "tool0"} or {"tool": "tool1"}
            - str: e.g. "tool0" (legacy)
            - None
        """
        try:
            # Normalize params to a dict
            if isinstance(params, str):
                params = {'tool': params}
            elif params is None:
                params = {}
            elif not isinstance(params, dict):
                params = {}

            # If a tool is provided, use it to set active extruder
            tool = params.get('tool')
            if isinstance(tool, str) and tool.startswith('tool'):
                try:
                    # Force single nozzle compliance
                    tool = force_single_tool(tool)
                    nozzle_index = int(tool.replace('tool', ''))
                    self.setActiveExtruder(nozzle_index)
                except Exception:
                    # ignore malformed tool string
                    pass
            self.changeFilament()
        except Exception as e:
            logger.error(f"Error in ChangeFilament.setup: {e}", exc_info=True)
            dialog.WarningOk(self, f"Error in ChangeFilament.setup: {e}", overlay=True)

    def changeFilamentDone(self):
        """Finalize the operation, persist tool state, and return to main screen."""
        logger.info("ChangeFilament.changeFilamentDone started")
        try:
            self._stop_inactivity_timer()
            # Persist tool state only if a load/unload operation was initiated
            if self.loadFlag is not None:
                try:
                    tool_key = f"tool{int(self.activeExtruder)}"
                    bay = self.main_window.printer_model.get_default_bay(tool_key)
                    # Determine selected filament name if any
                    selected = None
                    try:
                        selected_text = self.changeFilamentComboBox.currentText()
                        if selected_text and selected_text != "Loaded Filament":
                            selected = selected_text
                    except Exception:
                        # If combobox is unavailable, keep existing filament on load
                        selected = None

                    if bool(self.loadFlag):
                        # Loading: status Loaded; filament to selected (if provided), else unchanged
                        self.model.update_tool_bay_state(tool_key, bay=bay, filament=selected, status="Loaded", persist=True)
                    else:
                        # Unloading: status Empty; filament cleared
                        self.model.update_tool_bay_state(tool_key, bay=bay, filament=None, status="Empty", persist=True)
                except Exception as e:
                    logger.warning(f"Failed to persist tool state on filament change done: {e}")

            self._disconnect_temperature_signal()
            self.stackedWidget.setCurrentWidget(self.changeFilamentPage)  # Stops retract and extruding loop as well
            self.main_window.filament_management_screen.show_material_nozzle_screen()
            self.changeFilamentHeatingFlag = False
            # Reset the flag to avoid unintended reuse
            self.loadFlag = None
        except Exception as e:
            logger.error(f"Error in ChangeFilament.changeFilamentDone: {e}")
            dialog.WarningOk(self, f"Error in ChangeFilament.changeFilamentDone: {e}", overlay=True)

    # ---------------------
    # Internal helper utils
    # ---------------------
    def _jog_to_purge_position(self):
        """Jog the printer to the purge position for the active extruder, if safe to move."""
        try:
            if self.model.printer_status not in ["Printing", "Paused"]:
                purge_pos = self.model.tool1PurgePosition if self.activeExtruder == 1 else self.model.tool0PurgePosition
                self.octoprint_client.jog(purge_pos['X'], purge_pos['Y'], absolute=True, speed=10000)
        except Exception as e:
            logger.error(f"Error jogging to purge position: {e}")

    def _set_tool_temperature(self):
        """If a material is selected (not the 'Loaded' placeholder), set the tool temperature."""
        try:
            selected = str(self.changeFilamentComboBox.currentText())
            tool_key = f"tool{self.activeExtruder}"
            temp = self.model.filaments.get(selected)
            if temp is not None:
                self.octoprint_client.setToolTemperature({tool_key: temp})
        except Exception as e:
            logger.error(f"Error setting tool temperature: {e}")