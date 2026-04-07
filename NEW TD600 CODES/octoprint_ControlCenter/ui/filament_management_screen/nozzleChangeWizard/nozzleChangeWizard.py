"""
Nozzle Change Wizard
====================

User-guided UI flow for replacing the nozzle, driven by `nozzleChangeWizard.ui`.

Wizard steps (0-based indices → user-visible 1..6)
-------------------------------------------------
1. Step 1 (Intro):
	- Gate the Next button for ~10 seconds to avoid skipping before initial movements.
	- Run preflight checks (filament unloaded, tool cool) and safe initial moves if printer is idle.
2. Step 2 (Disconnect):
	- Disconnect OctoPrint while keeping the websocket connected.
3. Step 3 (Remove Nozzle):
	- Show instructions and media for nozzle removal.
4. Step 4 (Select Nozzle):
	- Let the user pick a nozzle size; persist selection into the model.
5. Step 5 (Check Connection):
	- Reconnect OctoPrint, restart Klipper, wait for Operational + Klipper Ready.
	- Sample tool temperature (several valid readings) to validate connection.
	- Use the progress bar to reflect stages; advance to Done when validated.
6. Step 6 (Done):
	- Show success instructions/media and allow returning to the material/nozzle screen.

What’s implemented now
----------------------
- UI loading and core widget wiring.
- Basic Next/Cancel navigation, step label updates.
- Step 5 progress bar reflecting reconnection and temperature sampling.
- Media (GIF) loading and per-page playback.
- Model-driven status (printer and Klipper state) gating logic.

Future hooks (extend as needed)
-------------------------------
- Additional safety checks and motion commands.
- More granular error handling and user guidance.
"""

import os
import time
from PyQt5 import uic, QtCore, QtGui
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QLabel, QProgressBar, QComboBox

from utils.helpers import check_ui_elements, run_async
from utils.logger import get_logger
from utils.printer_ui_config import force_single_tool
from utils import dialog
# Use machineBuildSize from the printer model instead of importing config here


class NozzleChangeWizard(QWidget):
	"""Wizard widget to guide the user through nozzle replacement.

	Responsibilities (current):
	- Load and bind UI elements.
	- Provide basic navigation and step labeling.
	- Simulate the connection check on step 5 using a timer-driven progress bar.

	Later:
	- Integrate motion/heating commands and real connection checks.
	- Load instructional GIFs.
	"""

	# Step indices (0-based) for clarity
	STEP_INTRO = 0
	STEP_DISCONNECT = 1
	STEP_REMOVE_NOZZLE = 2
	STEP_SELECT_NOZZLE = 3
	STEP_CHECK_CONNECTION = 4
	STEP_DONE = 5
	TOTAL_STEPS = 6

	def __init__(self, main_window):
		super().__init__()
		self.main_window = main_window
		# These are commonly present throughout the app; guard if missing.
		self.model = main_window.printer_model
		self.octoprint_client = getattr(main_window, "octoprint_client", None)
		self.active_tool = "tool0"  # default; updated in setup()
		self._did_initial_move = False  # run movement once per open

		self.logger = get_logger(self.__class__.__name__)
		self.logger.info("Initializing NozzleChangeWizard")

		# Load UI
		try:
			ui_file_path = os.path.join(os.path.dirname(__file__), "nozzleChangeWizard.ui")
			uic.loadUi(ui_file_path, self)
			self.logger.debug("nozzleChangeWizard UI loaded")
		except Exception as e:
			self.logger.error(f"Failed to load nozzleChangeWizard UI: {e}", exc_info=True)
			dialog.WarningOk(self, f"Failed to load Nozzle Change Wizard UI: {e}", overlay=True)
			return

		# Bind UI elements
		self.stackedWidget: QStackedWidget = self.findChild(QStackedWidget, "stackedWidget")
		self.stepLabel: QLabel = self.findChild(QLabel, "stepLabel")

		# Step pages (optional to hold references explicitly)
		self.step1Page: QWidget = self.findChild(QWidget, "step1Page")
		self.step2Page: QWidget = self.findChild(QWidget, "step2Page")
		self.step3Page: QWidget = self.findChild(QWidget, "step3Page")
		self.step4Page: QWidget = self.findChild(QWidget, "step4Page")
		self.step5Page: QWidget = self.findChild(QWidget, "step5Page")
		self.step6Page: QWidget = self.findChild(QWidget, "step6Page")

		# Media labels for GIFs (optional loading later)
		self.step2Gif: QLabel = self.findChild(QLabel, "step2Gif")
		self.step3Gif: QLabel = self.findChild(QLabel, "step3Gif")
		self.step4Gif: QLabel = self.findChild(QLabel, "step4Gif")
		self.step6Gif: QLabel = self.findChild(QLabel, "step6Gif")

		# Step 5 specifics
		self.step5Label: QLabel = self.findChild(QLabel, "step5Label")
		self.nozzleCheckProgressBar: QProgressBar = self.findChild(QProgressBar, "nozzleCheckProgressBar")

		# Step 4 specifics (nozzle selection)
		self.changeNozzleComboBox: QComboBox = self.findChild(QComboBox, "changeNozzleComboBox")

		# Buttons
		self.nextButton: QPushButton = self.findChild(QPushButton, "step1NextButton")
		self.cancelButton: QPushButton = self.findChild(QPushButton, "step1CancelButton")

		# Validate required elements
		required = [
			self.stackedWidget,
			self.stepLabel,
			self.step1Page, self.step2Page, self.step3Page, self.step4Page, self.step5Page, self.step6Page,
			self.nozzleCheckProgressBar,
			self.changeNozzleComboBox,
			self.nextButton, self.cancelButton,
		]
		check_ui_elements(self, required, "NozzleChangeWizard")

		# State
		self._current_step = 0
		self._progress_timer = QtCore.QTimer(self)
		self._progress_timer.setInterval(50)  # ms
		self._progress_timer.timeout.connect(self._advance_nozzle_check_progress)

		# Connection handling flags (disconnect REST during step 2; keep WS running)
		self._octoprint_was_disconnected = False
		self._octoprint_reconnected = False
		self._awaiting_reconnect_validation = False
		self._reconnect_timeout_timer = QtCore.QTimer(self)
		self._reconnect_timeout_timer.setSingleShot(True)
		# Temp checking state for step 5
		self._temp_check_timer = QtCore.QTimer(self)
		self._temp_check_timer.setInterval(500)
		self._temp_check_timer.timeout.connect(self._temp_check_tick)
		self._temp_check_attempts = 0
		self._temp_check_valid = 0

		# Step 1 guard: disable Next for at least 10 seconds on intro
		self._step1_guard_timer = QtCore.QTimer(self)
		self._step1_guard_timer.setSingleShot(True)
		# Inline handler: when guard elapses and we're still on Step 1, enable Next
		self._step1_guard_timer.timeout.connect(lambda: self._enable_next(True) if self._current_step == self.STEP_INTRO else None)

		# Wire signals
		self.nextButton.clicked.connect(self.on_next_clicked)
		self.cancelButton.clicked.connect(self.on_cancel_clicked)
		# Listen to Klipper state via the printer model (controller wires websocket -> model)
		self._klipper_ready = False
		self.model.klipper_state_changed.connect(self._on_klipper_state)
		try:
			ks = getattr(self.model, 'klipper_state', None)
			self._on_klipper_state(ks)
		except Exception:
			pass

		# Start at step 1
		self.goto_step(self.STEP_INTRO)

		# Preload videos from resources and hook page-change playback (unified terminology)
		self._resource_dir = os.path.join(os.path.dirname(__file__), "resources")
		# (page_index, target_label, file_name) - standardized to match CameraToolOffsetCalibration
		self._video_specs = [
			(1, self.step2Gif, "1_Cover Removal .gif"),
			(2, self.step3Gif, "2_Nozzle Removal.gif"),
			(3, self.step4Gif, "3_Nozzle Install.gif"),
			(5, self.step6Gif, "4_Cover Install.gif"),
		]
		self._video_movies = {}  # page_index -> QMovie (unified naming)
		
		# Video playback state tracking (unified with CameraToolOffsetCalibration)
		self.current_video_widget = None
		self.current_movie = None  # Currently playing QMovie object
		
		self._load_step_videos_safe()
		if self.stackedWidget:
			self.stackedWidget.currentChanged.connect(self._on_page_changed)
			# Initialize playback for current page
			self._on_page_changed(self.stackedWidget.currentIndex())

	# ----- Qt events -----------------------------------------------------
	# Redundantly called buy setup(), so commenting out
	# def showEvent(self, event):  # noqa: N802 (Qt naming)
	# 	"""Reset the wizard UI to Step 1 each time the widget is shown.

	# 	Keep this method light (avoid doing work here); initialization runs in
	# 	`setup()`/`changeNozzle()` and movement helpers.
	# 	"""
	# 	super().showEvent(event)
	# 	# Match ChangeFilamentWizard: keep showEvent light and only reset the UI
	# 	try:
	# 		self.changeNozzle()
	# 		self.logger.debug("Reset stacked widget to step 1 on show")
	# 	except Exception as e:
	# 		self.logger.warning(f"Error resetting wizard on show: {e}")

	def changeNozzle(self):
		"""Initialize and prepare the nozzle change flow (called from `setup`).

		Performs preflight checks and a safe initial move (home and position) if idle.
		"""
		self.logger.info("NozzleChange.changeNozzle() started")
		# Reset movement gate so each entry can perform the initial move if safe
		self._did_initial_move = False
		try:
			self.goto_step(self.STEP_INTRO)
			tool_str = self.active_tool or "tool0"
			# Preflight: filament unloaded and tool cool
			if not self._check_filament_unloaded(tool_str):
				return
			if not self._check_tool_cool(tool_str):
				return
			# Motion: if safe and idle, home and move
			self._perform_initial_move_if_safe()
		except Exception as e:
			self.logger.error(f"Error initializing nozzle change: {e}")

	# ----- Public API for parent screen -----------------------------------
	def setup(self, params=None):
		"""Prepare wizard with optional parameters.

		Params may be a dict like {"tool": "tool0"} or a str "tool0".
		"""
		try:
			tool = None
			if isinstance(params, dict):
				tool = params.get("tool")
			elif isinstance(params, str):
				tool = params
			# Force tool1 to tool0 for single nozzle configuration
			tool = force_single_tool(tool)
			if tool in ("tool0", "tool1"):
				self.active_tool = tool
			self.logger.info(f"NozzleChangeWizard.setup: active_tool={self.active_tool}")
			# Kick off the nozzle change flow like ChangeFilamentWizard.changeFilament()
			self.changeNozzle()
		except Exception as e:
			self.logger.error(f"Error in NozzleChangeWizard.setup: {e}")

	# ----- Navigation -----------------------------------------------------
	def goto_step(self, index: int):
		"""Switch to the given step index (0-based) and run step-entry hooks."""
		index = max(0, min(index, self.TOTAL_STEPS - 1))
		prev_step = getattr(self, "_current_step", 0)

		# 2) Commit the step change in UI
		self._current_step = index
		if self.stackedWidget:
			self.stackedWidget.setCurrentIndex(index)
		self._update_step_label()

		# 3) Enter/leave logic organized by step order
		# Step 1: Intro guard
		if index == self.STEP_INTRO:
			try:
				if self._step1_guard_timer.isActive():
					self._step1_guard_timer.stop()
				self._enable_next(False)  # re-arm guard
				self._step1_guard_timer.start(10000)
			except Exception:
				pass
		elif prev_step == self.STEP_INTRO:
			try:
				if self._step1_guard_timer.isActive():
					self._step1_guard_timer.stop()
			except Exception:
				pass

		# Step 2: Disconnect on entry
		if index == self.STEP_DISCONNECT:
			self._disconnect_printer_soft()

		# Step 4: Prepare selection UI on entry, teardown when leaving
		if index == self.STEP_SELECT_NOZZLE:
			self._prepare_step4()
		elif prev_step == self.STEP_SELECT_NOZZLE:
			self._teardown_step4()

		# Step 5: Reconnect/validate on entry; otherwise ensure teardown
		if index == self.STEP_CHECK_CONNECTION:
			nozzle = self.changeNozzleComboBox.currentText()
			try:
				self.model.update_tool_bay_state(self.active_tool, nozzle=nozzle, persist=True)
				self.logger.info(f"Persisted nozzle '{nozzle}' for {self.active_tool}")
			except Exception as e:
				self.logger.warning(f"Unable to persist nozzle selection: {e}")
			self._begin_reconnect_validation()
		else:
			self._teardown_step5_connections()
			self._stop_nozzle_check()

		# 4) Next button state/text
		if self.nextButton:
			self.nextButton.setText("Done" if index == self.STEP_DONE else "Next")
			if index == self.STEP_CHECK_CONNECTION:
				self._enable_next(False)
			elif index == self.STEP_SELECT_NOZZLE:
				self._enable_next(bool(self.changeNozzleComboBox and self.changeNozzleComboBox.currentIndex() > 0))
			elif index == self.STEP_INTRO:
				self._enable_next(False)  # guard will enable later
			else:
				self._enable_next(True)

	def on_next_clicked(self):
		"""Handle Next button clicks, including Done semantics on final step.

		Persistence for nozzle selection during Step 4 -> 5 transition is handled in goto_step.
		"""
		try:
			# If we are on the last step, treat Next as Done
			if self._current_step >= self.STEP_DONE:
				self.on_finish_clicked()
				return
			# If we are on step 5, Next is disabled until progress completes.
			self.goto_step(self._current_step + 1)
		except Exception as e:
			self.logger.error(f"Error advancing to next step: {e}")

	def on_cancel_clicked(self):
		"""Cancel the wizard and return to the Material/Nozzle screen.

		If REST was disconnected earlier, attempt a soft reconnect first.
		"""
		try:
			self._stop_nozzle_check()
			# If we previously disconnected in step 2 and haven't reconnected, reconnect now
			if self._octoprint_was_disconnected and not self._octoprint_reconnected:
				self._connect_printer_soft()
			# Clean up video resources (unified cleanup)
			self._release_video_resources()
			# Return to the filament management screen if available
			self.main_window.filament_management_screen.show_material_nozzle_screen()
			# Reset to step 1 for the next open
			self.goto_step(0)
		except Exception as e:
			self.logger.error(f"Error cancelling nozzle change wizard: {e}")
			dialog.WarningOk(self, f"Error cancelling Nozzle Change Wizard: {e}", overlay=True)

	def on_finish_clicked(self):
		"""Finish the wizard and return to the main Material/Nozzle page."""
		try:
			self._stop_nozzle_check()
			# Ensure we reconnect if we had disconnected earlier
			if self._octoprint_was_disconnected and not self._octoprint_reconnected:
				self._connect_printer_soft()
			self.main_window.filament_management_screen.show_material_nozzle_screen()
			# Reset to step 1 ready for next open
			self.goto_step(0)
			self._stop_all_videos()
		except Exception as e:
			self.logger.error(f"Error finishing nozzle change wizard: {e}")

	def _update_step_label(self):
		"""Update the "Step X/Y" label to match the current index."""
		try:
			if self.stepLabel:
				self.stepLabel.setText(f"Step {self._current_step + 1}/{self.TOTAL_STEPS}")
		except Exception:
			pass



	# ----- Step 5: Nozzle connection check (simulated) -------------------
	def _start_nozzle_check(self):
		"""Start the simulated nozzle connection check (progress bar).

		This is a UI helper for step visuals; the real validation happens during
		reconnection and temperature sampling.
		"""
		try:
			self._set_step5_status("Checking Nozzle Connection ...", 0)
			self._progress_timer.start()
			self._enable_next(False)
		except Exception as e:
			self.logger.warning(f"Failed to start nozzle check simulation: {e}")

	def _advance_nozzle_check_progress(self):
		"""Increment progress bar and auto-advance on completion (simulated)."""
		try:
			if not self.nozzleCheckProgressBar:
				return
			value = self.nozzleCheckProgressBar.value() + 2
			if value >= 100:
				value = 100
				self._stop_nozzle_check()
				if self.step5Label:
					self.step5Label.setText("Nozzle connection OK")
				# Auto-advance to step 6 after short delay
				QtCore.QTimer.singleShot(300, lambda: self.goto_step(5))
				return
			self.nozzleCheckProgressBar.setValue(value)
		except Exception:
			# Keep UI responsive even if something goes wrong
			pass

	def _stop_nozzle_check(self):
		"""Stop the simulated nozzle check and restore Next if not on Step 5."""
		try:
			if self._progress_timer.isActive():
				self._progress_timer.stop()
			# Re-enable Next outside of step 5
			if self._current_step != self.STEP_CHECK_CONNECTION:
				self._enable_next(True)
		except Exception:
			pass

	# (preflight and motion handled via changeNozzle() called from setup)

	# ----- Video helpers --------------------------------------------------
	def _load_step_videos_safe(self):
		"""Initialize video storage for lazy loading."""
		self._video_movies.clear()
		self.logger.debug(f"Initialized video system with {len(self._video_specs)} video specifications")

	def _find_video_label(self, step_number):
		"""Find the label widget for a given step number."""
		for spec_step_number, label, _ in self._video_specs:
			if spec_step_number == step_number:
				return label
		return None

	def _ensure_video_loaded(self, step_number):
		"""
		Load video on-demand for the specified step.
		
		Args:
			step_number (int): Step number to ensure video is loaded for
			
		Returns:
			QMovie: Loaded QMovie object if successful, None otherwise
		"""
		if step_number in self._video_movies:
			return self._video_movies[step_number]
			
		try:
			for spec_step_number, label, fname in self._video_specs:
				if spec_step_number == step_number and label and fname:
					video_path = os.path.join(self._resource_dir, fname)
					
					if not os.path.exists(video_path):
						self.logger.warning(f"Video file not found for step {step_number}: {video_path}")
						return None
					
					movie = QtGui.QMovie(video_path)
					if not movie.isValid():
						self.logger.warning(f"Video not valid for step {step_number}: {video_path}")
						return None
					
					movie.setCacheMode(QtGui.QMovie.CacheNone)
					self._video_movies[step_number] = movie
					self.logger.info(f"Video loaded on-demand for step {step_number}: {fname}")
					return movie
		except Exception as e:
			self.logger.error(f"Error loading video for step {step_number}: {e}")
		return None

	def _stop_all_videos(self):
		"""Stop all loaded video movies (unified system)."""
		for movie in list(self._video_movies.values()):
			try:
				movie.stop()
			except Exception:
				pass

	def _stop_current_video(self):
		"""Stop currently playing video and clear references."""
		if self.current_movie and self.current_movie.state() != QtGui.QMovie.NotRunning:
			self.current_movie.stop()
		if self.current_video_widget:
			self.current_video_widget.setMovie(None)
			self.current_video_widget.clear()
		self.current_movie = None
		self.current_video_widget = None

	def _release_video_resources(self):
		"""Release all video resources from memory."""
		self._stop_current_video()
		self._stop_all_videos()
		self._video_movies.clear()



	def _play_step_video(self, step_number):
		"""
		Play instructional video for the specified step.
		
		Args:
			step_number (int): Step number to play video for
		"""
		try:
			movie = self._ensure_video_loaded(step_number)
			if not movie:
				self.logger.warning(f"Could not load video for step {step_number}")
				return
			
			label_widget = self._find_video_label(step_number)
			if label_widget and movie:
				self._play_movie_in_label(movie, label_widget)
				self.logger.info(f"Playing step {step_number} instructional video")
			else:
				self.logger.warning(f"Video components not ready for step {step_number}")
				
		except Exception as e:
			self.logger.error(f"Error playing step {step_number} video: {e}")

	# Removed redundant _play_page_video alias - use _play_step_video directly

	def _play_movie_in_label(self, movie, label_widget):
		"""
		Play QMovie in the specified label widget (unified with CameraToolOffsetCalibration).
		
		Args:
			movie (QMovie): QMovie object to play
			label_widget (QLabel): Label widget to display video in
		"""
		try:
			# Stop any existing video using unified current video tracking
			self._stop_current_video()
			
			# Ensure movie is in stopped state before starting (fixes replay issues)
			if movie.state() != QtGui.QMovie.NotRunning:
				movie.stop()
			
			# Jump to start of animation for proper replay
			movie.jumpToFrame(0)
			
			# Set up the movie in the label with unified tracking
			label_widget.setMovie(movie)
			self.current_movie = movie
			self.current_video_widget = label_widget
			
			# Start playing the movie
			movie.start()
			
			self.logger.info(f"Started playing video in {label_widget.objectName()}")
			
		except Exception as e:
			self.logger.debug(f"Error playing movie in label: {e}")

	def _on_page_changed(self, idx: int):
		"""Play video for the current page."""
		try:
			self._stop_all_videos()
			self._play_step_video(idx)
		except Exception:
			pass

	def _on_klipper_state(self, state: str):
		"""Track whether Klipper is Ready (normalized lower-case check)."""
		self._klipper_ready = (str(state).strip().lower() == 'ready')

	# ----- Step 5: reconnect and validate temperature ---------------------
	def _begin_reconnect_validation(self):
		"""On step 5, reconnect to printer, wait for Operational, reselect tool, validate temp, then advance or go back."""
		try:
			# Update UI for connection phase
			self._set_step5_status("Connecting to printer ...", 10)
			# Guard against multiple connections
			self._awaiting_reconnect_validation = True
			self._temp_check_attempts = 0
			self._temp_check_valid = 0
			# Fire the (soft) reconnect sequence
			self._connect_printer_soft()
			# Start async waiter for Operational + Klipper ready before any printer ops
			self._wait_for_ready_async()
		except Exception as e:
			self.logger.warning(f"Failed to begin reconnect validation: {e}")

	def _teardown_step5_connections(self):
		"""Stop timers and clear flags when leaving Step 5 validation."""
		try:
			if self._reconnect_timeout_timer.isActive():
				self._reconnect_timeout_timer.stop()
			if self._temp_check_timer.isActive():
				self._temp_check_timer.stop()
			self._awaiting_reconnect_validation = False
		except Exception:
			pass

	@run_async
	def _wait_for_ready_async(self):
		"""Background wait until printer is Operational and Klipper is ready, or timeout."""
		deadline = time.time() + 60.0
		ready = False
		while time.time() < deadline and self._awaiting_reconnect_validation:
			try:
				status = str(getattr(self.model, 'printer_status', '')).strip().lower()
				if status == 'operational' and self._klipper_ready:
					ready = True
					break
			except Exception:
				pass
			time.sleep(1)
		if not self._awaiting_reconnect_validation:
			return
		if not ready:
			QtCore.QTimer.singleShot(0, lambda: self._handle_reconnect_failure("Unable to reconnect to the printer. Please check connections and try again."))
			return
		# Ready: proceed on main thread
		QtCore.QTimer.singleShot(0, self._on_ready_then_check)

	def _on_ready_then_check(self):
		"""On main thread: after printer is ready, select tool and begin temp check."""
		if not self._awaiting_reconnect_validation:
			return
		# Update UI and progress
		self._set_step5_status("Connected. Checking nozzle temperature ...", 70)
		# Select the correct tool now that Klipper is ready
		try:
			tool_idx = int((self.active_tool or "tool0").replace("tool", "") or 0)
			self.octoprint_client.selectTool(tool_idx)
		except Exception:
			pass
		# Start temperature validation shortly
		QtCore.QTimer.singleShot(500, self._validate_reconnect_temperature)

	def _handle_reconnect_failure(self, message: str):
		"""Show a warning and route the user back to Step 4 on failure."""
		self._awaiting_reconnect_validation = False
		try:
			dialog.WarningOk(self, message, overlay=True)
			QtCore.QTimer.singleShot(0, lambda: self.goto_step(3))
		except Exception:
			pass

	def _validate_reconnect_temperature(self):
		"""Start periodic temperature sampling to avoid junk readings and reflect progress."""
		if not self._awaiting_reconnect_validation:
			return
		try:
			# Initialize sampling counters
			self._temp_check_attempts = 0
			self._temp_check_valid = 0
			self._set_step5_status(None, 75)
			self._temp_check_timer.start()
		except Exception as e:
			self.logger.warning(f"Failed to start temperature sampling: {e}")

	def _temp_check_tick(self):
		"""Sample tool temperature and accumulate valid readings to pass validation."""
		if not self._awaiting_reconnect_validation:
			self._temp_check_timer.stop()
			return
		try:
			self._temp_check_attempts += 1
			tool_idx = int((self.active_tool or "tool0").replace("tool", "") or 0)
			temps = getattr(self.model, 'temperatures', {}) or {}
			actual = temps.get(f'tool{tool_idx}Actual')
			try:
				actual_val = float(actual) if actual is not None else None
			except Exception:
				actual_val = None
			if actual_val is not None and 15 <= actual_val <= 50:
				self._temp_check_valid += 1
				# Increase progress for valid samples towards 100
				if self.nozzleCheckProgressBar:
					base = 75
					inc = min(self._temp_check_valid, 3) * 8  # 75 -> 99 over 3 valid samples
					self.nozzleCheckProgressBar.setValue(min(base + inc, 99))
			# Decide outcome
			if self._temp_check_valid >= 3:
				self._temp_check_timer.stop()
				self._set_step5_status("Nozzle connection OK", 100)
				self._awaiting_reconnect_validation = False
				QtCore.QTimer.singleShot(200, lambda: self.goto_step(5))
				return
			# Allow up to 50 attempts total before failing
			if self._temp_check_attempts >= 50 and self._temp_check_valid < 3:
				self._temp_check_timer.stop()
				try:
					dialog.WarningOk(self, "There was a connection issue. Please recheck the connections.", overlay=True)
					QtCore.QTimer.singleShot(0, lambda: self.goto_step(3))
				finally:
					self._awaiting_reconnect_validation = False
		except Exception as e:
			self._temp_check_timer.stop()
			self._awaiting_reconnect_validation = False
			self.logger.warning(f"Temperature sampling failed: {e}")

	def _on_reconnect_timeout(self):
		"""Fallback timeout handler if Operational state isn't reached in time."""
		# Could not reach Operational in time
		self._reconnect_timeout_timer.stop()
		if not self._awaiting_reconnect_validation:
			return
		try:
			dialog.WarningOk(self, "Unable to reconnect to the printer. Please check connections and try again.", overlay=True)
			QtCore.QTimer.singleShot(0, lambda: self.goto_step(3))
		finally:
			self._awaiting_reconnect_validation = False

	# ----- Connection helpers --------------------------------------------
	def _disconnect_printer_soft(self):
		"""Disconnect the printer via REST, keeping our websocket client running."""
		if not self.octoprint_client:
			return
		try:
			self.octoprint_client.disconnect()
			self._octoprint_was_disconnected = True
			self._octoprint_reconnected = False
			self.logger.info("OctoPrint REST: disconnect command sent (websocket remains connected)")
		except Exception as e:
			self.logger.warning(f"Failed to disconnect printer (soft): {e}")

	def _connect_printer_soft(self):
		"""Reconnect the printer via REST using saved settings."""
		if not self.octoprint_client:
			return
		try:
			# Connect to Klipper's virtual serial at the expected port and baudrate
			self.octoprint_client.connectPrinter(port="/tmp/printer", baudrate=115200)
			self.nozzleCheckProgressBar.setValue(30)
			# Issue Klipper restarts after a short delay to allow the serial link to be ready
			self.step5Label.setText("Restarting Klipper ...")
			self.nozzleCheckProgressBar.setValue(50)
			self._octoprint_reconnected = True
			self.logger.info("OctoPrint REST: connect command sent")
		except Exception as e:
			self.logger.warning(f"Failed to reconnect printer (soft): {e}")


	# ----- Step 4: Nozzle selection ---------------------------------------
	def _prepare_step4(self):
		"""Populate nozzle options and enforce selection before proceeding."""
		try:
			try:
				self.changeNozzleComboBox.currentIndexChanged.disconnect(self._on_nozzle_choice_changed)
			except Exception:
				pass

			self.changeNozzleComboBox.clear()
			self.changeNozzleComboBox.addItem("Select Size")
			options = []
			if self.model is not None and hasattr(self.model, 'nozzle_options'):
				options = list(getattr(self.model, 'nozzle_options') or [])
			if not options:
				options = ["0.25", "0.4", "0.6", "0.8", "1.0"]
			for opt in options:
				self.changeNozzleComboBox.addItem(str(opt))

			# Next enabled only when a real selection is made
			if self.nextButton:
				self.nextButton.setEnabled(self.changeNozzleComboBox.currentIndex() > 0)

			self.changeNozzleComboBox.currentIndexChanged.connect(self._on_nozzle_choice_changed)
		except Exception as e:
			self.logger.warning(f"Failed to prepare step 4: {e}")

	def _teardown_step4(self):
		"""Disconnect Step 4 combo change signals to avoid duplicate handlers."""
		try:
			if self.changeNozzleComboBox:
				try:
					self.changeNozzleComboBox.currentIndexChanged.disconnect(self._on_nozzle_choice_changed)
				except Exception:
					pass
		except Exception:
			pass

	def _on_nozzle_choice_changed(self, idx: int):
		"""Enable Next only when a valid nozzle size is selected (index > 0)."""
		try:
			if self.nextButton:
				self.nextButton.setEnabled(idx > 0)
		except Exception:
			pass



	# ----- Helpers: readability and reuse ---------------------------------
	def _enable_next(self, enabled: bool):
		"""Safely enable/disable the Next button."""
		try:
			if self.nextButton:
				self.nextButton.setEnabled(bool(enabled))
		except Exception:
			pass

	def _set_step5_status(self, text: str = None, progress: int = None):
		"""Helper to update Step 5 status label and/or progress bar value."""
		if text is not None and self.step5Label:
			self.step5Label.setText(text)
		if progress is not None and self.nozzleCheckProgressBar:
			self.nozzleCheckProgressBar.setValue(int(progress))

	def _show_material_nozzle_screen_and_return(self):
		"""Return to the parent Material/Nozzle screen and signal caller to stop."""
		fms = getattr(self.main_window, "filament_management_screen", None)
		if fms and hasattr(fms, "show_material_nozzle_screen"):
			QtCore.QTimer.singleShot(0, lambda: fms.show_material_nozzle_screen())
		return False

	def _get_tool_index(self, tool: str) -> int:
		"""Extract numeric index from a tool name like 'tool0' or 'tool1'."""
		try:
			return int((tool or "tool0").replace('tool', '') or 0)
		except Exception:
			return 0

	def _is_printer_idle(self) -> bool:
		"""Return True if not printing or paused, based on model.printer_status."""
		status = (str(getattr(self.model, 'printer_status', '')) or '').lower()
		return status not in ('printing', 'paused')

	def _check_filament_unloaded(self, tool: str) -> bool:
		"""Warn and exit if the bay status indicates filament is still loaded."""
		try:
			state = self.model.get_bay_state(tool) or {}
			if str(state.get('status')) == 'Loaded':
				dialog.WarningOk(self, "Filament is loaded. Please unload filament before changing the nozzle.", overlay=True)
				return self._show_material_nozzle_screen_and_return()
			return True
		except Exception:
			return True

	def _check_tool_cool(self, tool: str) -> bool:
		"""Warn and exit if the selected tool is above a safe touch temperature."""
		try:
			temps = self.model.temperatures or {}
			tool_idx = self._get_tool_index(tool)
			t = temps.get(f'tool{tool_idx}') or temps.get(f'tool{tool_idx}Actual')
			if t is not None and float(t) > 50:
				dialog.WarningOk(self, "Tool temperature is too high to touch (> 50°C). Please initiate cooling and wait for it to be cool enough to touch", overlay=True)
				return self._show_material_nozzle_screen_and_return()
			return True
		except Exception:
			return True

	def _perform_initial_move_if_safe(self):
		"""Home, select tool, and move to a safe position if the printer is idle."""
		try:
			if self._did_initial_move or not self._is_printer_idle():
				return
			size = self.model.machineBuildSize
			x = int((size.get('X') or 0) / 2)
			y = 0.0
			if self.octoprint_client:
				self.octoprint_client.gcode("G90")
				self.octoprint_client.gcode("G28")
				try:
					tool_idx = self._get_tool_index(self.active_tool)
					self.octoprint_client.selectTool(tool_idx)
				except Exception:
					pass
				self.octoprint_client.jog(z=-10, absolute=False, speed=1800)
				self.octoprint_client.jog(x=x, y=y, absolute=True, speed=6000)
			self._did_initial_move = True
		except Exception as move_err:
			self.logger.warning(f"Initial move skipped: {move_err}")

