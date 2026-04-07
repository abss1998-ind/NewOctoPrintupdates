import os
from PyQt5.QtWidgets import QWidget, QToolButton, QPushButton, QStackedWidget, QLabel
from PyQt5 import QtWidgets, QtCore
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5 import uic
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils.printer_ui_config import apply_nozzle_config_to_screen
from utils import dialog
from utils import styles
import config
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QFormLayout, QComboBox

# Import sub-screens
from ui.filament_management_screen.changeFilamentWizard.changeFilamentWizard import ChangeFilamentWizard
from ui.filament_management_screen.nozzleChangeWizard.nozzleChangeWizard import NozzleChangeWizard

logger = get_logger(__name__)

class filamentManagementScreen(QWidget):
    def __init__(self, main_window):
        """Initialize the combined Filament/Nozzle screen, create sub-screens,
        wire up controls, and set initial UI state.

        Args:
            main_window: Reference to the main window to access shared services and navigation.
        """
        super(filamentManagementScreen, self).__init__()
        self.main_window = main_window
        self.octoprint_client = main_window.octoprint_client
        self.logger = get_logger(self.__class__.__name__)

        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "filamentManagementScreen.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("filamentManagementScreen UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load filamentManagementScreen UI file: {e}")

        # Initialize UI components
        self.material_nozzle_stacked_widget = self.findChild(QStackedWidget, "mainMaterialNozzleStackedWidget")
        self.main_material_nozzle_page = self.findChild(QWidget, "mainMaterialNozzlePage")

        # Material buttons (simplified: one per tool)
        self.changeTool0MaterialBayA = self.findChild(QToolButton, "changeTool0MaterialBayA")
        self.changeTool1MaterialBayX = self.findChild(QToolButton, "changeTool1MaterialBayX")

        # Nozzle buttons
        self.changeTool0Button = self.findChild(QToolButton, "changeTool0Button")
        self.changeTool1Button = self.findChild(QToolButton, "changeTool1Button")

        # Labels and state indicators
        self.tool0MaterialBayALabel = self.findChild(QLabel, "tool0MaterialBayALabel")
        self.tool1MaterialBayXLabel = self.findChild(QLabel, "tool1MaterialBayXLabel")
        self.tool0MaterialBayAStateLabel = self.findChild(QLabel, "tool0MaterialBayAStateLabel")
        self.tool1MaterialBayXStateLabel = self.findChild(QLabel, "tool1MaterialBayXStateLabel")
        self.tool0MaterialBayAStateColor = self.findChild(QLabel, "tool0MaterialBayAStateColor")
        self.tool11MaterialBayXStateColor = self.findChild(QLabel, "tool11MaterialBayXStateColor")

        # Edit buttons
        self.editTool0MaterialBayA = self.findChild(QPushButton, "editTool0MaterialBayA")
        # UI now corrected to editTool1MaterialBayX as per user
        self.editTool1MaterialBayX = self.findChild(QPushButton, "editTool1MaterialBayX") or \
                                     self.findChild(QPushButton, "editTool0MaterialBayX")

        # Back button
        self.materialNozzleBackButton = self.findChild(QPushButton, "materialNozzleBackButton")

        # Validate UI components
        # Validate only elements that exist (labels showing loaded filament were removed from the UI)
        check_ui_elements(self, [
            self.material_nozzle_stacked_widget, self.main_material_nozzle_page,
            self.changeTool0MaterialBayA, self.changeTool1MaterialBayX,
            self.changeTool0Button, self.changeTool1Button,
            self.materialNozzleBackButton,
            self.tool0MaterialBayAStateLabel, self.tool1MaterialBayXStateLabel,
            self.tool0MaterialBayAStateColor, self.tool11MaterialBayXStateColor,
            self.editTool0MaterialBayA, self.editTool1MaterialBayX
        ], "filamentManagementScreen")

        # Initialize all sub-screens
        self.screens = {}
        self._initialize_sub_screens()

        # Connect buttons to their respective methods (no bay parameter anymore)
        self.changeTool0MaterialBayA.clicked.connect(
            lambda: self.show_material_nozzle_screen(target_screen="filament_change", params={"tool": "tool0"})
        )
        self.changeTool1MaterialBayX.clicked.connect(
            lambda: self.show_material_nozzle_screen(target_screen="filament_change", params={"tool": "tool1"})
        )

        self.changeTool0Button.clicked.connect(
            lambda: self.show_material_nozzle_screen(target_screen="nozzle_change", params={"tool": "tool0"})
        )
        self.changeTool1Button.clicked.connect(
            lambda: self.show_material_nozzle_screen(target_screen="nozzle_change", params={"tool": "tool1"})
        )

        # Edit handlers
        if self.editTool0MaterialBayA:
            self.editTool0MaterialBayA.clicked.connect(lambda: self._open_edit_dialog("tool0"))
        if self.editTool1MaterialBayX:
            self.editTool1MaterialBayX.clicked.connect(lambda: self._open_edit_dialog("tool1"))

        self.materialNozzleBackButton.clicked.connect(lambda: self.main_window.switch_to_menu_screen())

        # Show the main material/nozzle page initially
        self.material_nozzle_stacked_widget.setCurrentWidget(self.main_material_nozzle_page)
        self.logger.debug("Set current widget to mainMaterialNozzlePage")
        self._loading_dialog = None
        # Bind to printer model signals for state updates
        try:
            self.main_window.printer_model.tool_bay_states_loaded.connect(self._on_tool_states_loaded)
            self.main_window.printer_model.tool_bay_state_changed.connect(self._on_tool_state_changed)
            # Also react to printer status to enable/disable change buttons
            self.main_window.printer_model.status_updated.connect(self._on_status_updated)
        except Exception as e:
            self.logger.error(f"Failed connecting tool state signals: {e}")
        # Apply current state immediately in case the signal fired before this screen connected
        try:
            if hasattr(self.main_window.printer_model, 'tools'):
                self._on_tool_states_loaded(self.main_window.printer_model.tools)
        except Exception as e:
            self.logger.debug(f"Unable to apply initial tool state: {e}")
        # Apply current printer status to buttons immediately
        try:
            self._on_status_updated(self.main_window.printer_model.printer_status)
        except Exception as e:
            self.logger.debug(f"Unable to apply initial status to buttons: {e}")

        # Apply nozzle configuration
        self.apply_nozzle_configuration()

    def apply_nozzle_configuration(self):
        """Hide dual nozzle elements for single nozzle configuration."""
        apply_nozzle_config_to_screen(self, 'filament_management_screen')

    def _on_status_updated(self, status: str):
        """Enable/disable change buttons based on printer status.

        Printing/Paused: disable only nozzle change; keep material change enabled.
        Offline: disable both types. Operational: enable all.
        """
        nozzle_disabled = status in ("Printing", "Paused", "Offline")
        material_disabled = status == "Offline"

        self.changeTool0Button.setDisabled(nozzle_disabled)
        self.changeTool1Button.setDisabled(nozzle_disabled)
        self.changeTool0MaterialBayA.setDisabled(material_disabled)
        self.changeTool1MaterialBayX.setDisabled(material_disabled)

    def showEvent(self, event):
        """Reset to main_material_nozzle_page whenever this widget is shown from main window navigation."""
        super().showEvent(event)
        try:
            self.material_nozzle_stacked_widget.setCurrentWidget(self.main_material_nozzle_page)
            self.logger.debug("Reset stacked widget to main_material_nozzle_page on show")
        except Exception as e:
            self.logger.error(f"Error resetting to main_material_nozzle_page: {e}")

    def _initialize_sub_screens(self):
        """Initialize all filament/nozzle sub-screens"""
        try:
            # Create instances of each sub-screen
            self.screens["filament_change"] = ChangeFilamentWizard(self.main_window)
            self.screens["nozzle_change"] = NozzleChangeWizard(self.main_window)

            # Add each screen to the stacked widget
            for name, screen in self.screens.items():
                self.material_nozzle_stacked_widget.addWidget(screen)
                self.logger.info(f"Added {name} screen to material/nozzle stacked widget")
            
        except Exception as e:
            self.logger.exception(f"Error initializing sub-screens: {e}")

    def _open_loading_dialog(self, message="Please wait, loading..."):
        """Show a lightweight non-blocking loading dialog using utils.dialog.

        Args:
            message: Message shown to the user while the sub-UI initializes.
        """
        try:
            if self._loading_dialog:
                return
            # Use centralized dialog helper (non-blocking, no buttons, with overlay)
            self._loading_dialog = dialog.dialog(
                self,
                message,
                buttons=QtWidgets.QMessageBox.NoButton,
                overlay=False,
                format_text=False
            )
            # Force a paint so the dialog is visible before doing heavy work
            QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents)
        except Exception as e:
            self.logger.error(f"Failed to show loading dialog: {e}")

    def _close_loading_dialog(self):
        """Safely hide and destroy the loading dialog if it is visible."""
        try:
            if self._loading_dialog:
                self._loading_dialog.hide()
                self._loading_dialog.deleteLater()
                self._loading_dialog = None
        except Exception as e:
            self.logger.error(f"Failed to close loading dialog: {e}")

    def _navigate_to_screen(self, screen, params, target_screen):
        """Finish navigation after the loading dialog has painted.

        Calls the sub-screen setup (if available), switches the stacked widget,
        and then closes the loading dialog.

        Args:
            screen: The QWidget sub-screen instance to show.
            params: Optional parameters forwarded to the sub-screen setup().
            target_screen: Name of the target screen for logging purposes.
        """
        try:
            if params and hasattr(screen, 'setup'):
                screen.setup(params)
            self.material_nozzle_stacked_widget.setCurrentWidget(screen)
            self.logger.info(f"Navigated to {target_screen}")
        except Exception as e:
            self.logger.exception(f"Failed navigating to {target_screen}: {e}")
        finally:
            self._close_loading_dialog()

    def show_material_nozzle_screen(self, target_screen=None, params=None):
        """Show the main page or navigate to a specific sub-screen."""
        self.logger.debug(f"show_material_nozzle_screen called with target_screen={target_screen}, params={params}")

        if self.main_window.current_screen != self:
            self.main_window.switch_screen(self)

        if not target_screen:
            self.material_nozzle_stacked_widget.setCurrentWidget(self.main_material_nozzle_page)
            self.logger.debug("Showing main material/nozzle page")
            return

        screen = self.screens.get(target_screen)
        if not screen:
            self.logger.error(f"Requested screen '{target_screen}' not found in available screens")
            return

        self._open_loading_dialog("Please wait, loading...")
        QtWidgets.QApplication.processEvents(QtCore.QEventLoop.AllEvents)
        QtCore.QTimer.singleShot(0, lambda: self._navigate_to_screen(screen, params, target_screen))

    # --- New: UI state updates from model ---
    def _status_to_style(self, status: str) -> str:
        # Mapping: Loaded=green, Unknown=red, Empty=amber, Staged=blue
        if status == "Loaded":
            return styles.printer_status_green
        if status == "Unknown":
            return styles.printer_status_red
        if status == "Empty":
            return styles.printer_status_amber
        if status == "Staged":
            return styles.printer_status_blue
        return styles.printer_status_amber

    def _apply_tool_ui(self, tool: str, data: dict):
        filament = data.get("filament") or "Unknown"
        status = data.get("status", "Unknown")
        display_filament = "-" if status == "Empty" else str(filament)
        nozzle = data.get("nozzle", "Unknown")
        if tool == "tool0":
            # Show currently loaded material on the button itself
            if self.changeTool0MaterialBayA:
                self.changeTool0MaterialBayA.setText(display_filament)
            if self.tool0MaterialBayAStateLabel:
                self.tool0MaterialBayAStateLabel.setText(str(status))
            if self.tool0MaterialBayAStateColor:
                self.tool0MaterialBayAStateColor.setStyleSheet(self._status_to_style(status))
            if self.changeTool0Button:
                self.changeTool0Button.setText("Unknown" if nozzle == "Unknown" or not nozzle else f"{nozzle} mm")
        elif tool == "tool1":
            if self.changeTool1MaterialBayX:
                self.changeTool1MaterialBayX.setText(display_filament)
            if self.tool1MaterialBayXStateLabel:
                self.tool1MaterialBayXStateLabel.setText(str(status))
            if self.tool11MaterialBayXStateColor:
                self.tool11MaterialBayXStateColor.setStyleSheet(self._status_to_style(status))
            if self.changeTool1Button:
                self.changeTool1Button.setText("Unknown" if nozzle == "Unknown" or not nozzle else f"{nozzle} mm")

    def _on_tool_states_loaded(self, states: dict):
        # Use primary bays for current UI
        m = self.main_window.printer_model
        t0 = m.get_bay_state("tool0")
        t1 = m.get_bay_state("tool1")
        self._apply_tool_ui("tool0", t0)
        self._apply_tool_ui("tool1", t1)

    def _on_tool_state_changed(self, tool: str, bay: str, data: dict):
        # For now, reflect only primary bay changes on screen
        if bay == self.main_window.printer_model.get_default_bay(tool):
            self._apply_tool_ui(tool, data)

    # --- New: Edit dialog to sync reality without wizard ---
    def _open_edit_dialog(self, tool: str):
        model = self.main_window.printer_model
        current = model.get_bay_state(tool)
        filament_names = list(getattr(model, 'filaments', config.filaments).keys())

        dialog_widget = QDialog(self)
        dialog_widget.setObjectName("EditToolStateDialog")
        # Title: Edit Tool * Material Bay ** (e.g., Tool 0, Bay A/X)
        try:
            default_bay = model.get_default_bay(tool)
            if default_bay:
                bay_letter = default_bay.split("_")[-1].upper()
            else:
                bay_letter = "A" if tool == "tool0" else "X"
            tool_num = tool.replace("tool", "") if isinstance(tool, str) else str(tool)
            dialog_widget.setWindowTitle(f"Edit Tool {tool_num} Material Bay {bay_letter}")
        except Exception:
            dialog_widget.setWindowTitle(f"Edit Tool State")
        # Make dialog larger and easier to read
        dialog_widget.setMinimumSize(450, 250)
        # Use shared dialog font (Gotham) for consistency with other dialogs (bumped +1pt)
        base_font = dialog.font(size=15)
        dialog_widget.setFont(base_font)
        # Keep the dialog visible above to avoid getting lost behind other widgets
        try:
            dialog_widget.setWindowFlags(dialog_widget.windowFlags() | Qt.WindowStaysOnTopHint)
            dialog_widget.setModal(True)
        except Exception:
            pass
        # Apply a light palette to avoid inherited dark theme artifacts
        try:
            pal = dialog_widget.palette()
            pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#ffffff"))
            pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#ffffff"))
            pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#f5f5f5"))
            pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#000000"))
            pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#000000"))
            pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#f5f5f5"))
            pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#000000"))
            pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#0078D7"))
            pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
            dialog_widget.setPalette(pal)
            dialog_widget.setAutoFillBackground(True)
        except Exception:
            pass
        # Ensure strong contrast with a white background while keeping native look
        try:
            dialog_widget.setStyleSheet(
                """
                #EditToolStateDialog, #EditToolStateDialog QWidget, #EditToolStateDialog QFrame { background-color: #ffffff; color: #000000; }
                #EditToolStateDialog QLabel { color: #000000; background-color: transparent; }
                #EditToolStateDialog QLineEdit, #EditToolStateDialog QComboBox { background-color: #ffffff; color: #000000; border: 1px solid #c7c7c7; border-radius: 4px; padding: 4px; padding-right: 30px; }
                #EditToolStateDialog QComboBox:!editable { background-color: #ffffff; }
                #EditToolStateDialog QComboBox::drop-down { background-color: #f0f0f0; border-left: 1px solid #c7c7c7; width: 30px; }
                #EditToolStateDialog QComboBox::down-arrow { image: url(:/Navigation/img/Navigation/arrows-5.png); width: 12px; height: 12px; }
                #EditToolStateDialog QComboBox QAbstractItemView, #EditToolStateDialog QComboBox QListView { background-color: #ffffff; color: #000000; selection-background-color: #0078D7; selection-color: #ffffff; }
                #EditToolStateDialog QListView { background-color: #ffffff; color: #000000; }
                #EditToolStateDialog QListView::item { padding: 6px 8px; }
                #EditToolStateDialog QPushButton { background-color: #f5f5f5; color: #000000; border: 1px solid #c7c7c7; border-radius: 4px; padding: 10px 18px; }
                #EditToolStateDialog QPushButton:disabled { color: #888888; }
                #EditToolStateDialog QDialogButtonBox QPushButton { min-width: 120px; }
                """
            )
        except Exception:
            pass
        form = QFormLayout(dialog_widget)
        try:
            form.setHorizontalSpacing(20)
            form.setVerticalSpacing(14)
            form.setContentsMargins(20, 20, 20, 12)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.setFormAlignment(Qt.AlignTop | Qt.AlignLeft)
            form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        except Exception:
            pass

        cb_filament = QComboBox(dialog_widget)
        cb_filament.setFont(base_font)
        try:
            cb_filament.setMinimumWidth(220)
        except Exception:
            pass
        try:
            cb_filament.setStyleSheet("QComboBox { background-color: #ffffff; color: #000000; } QComboBox QAbstractItemView, QComboBox QListView { background-color: #ffffff; color: #000000; selection-background-color: #0078D7; selection-color: #ffffff; }")
        except Exception:
            pass
        try:
            lv_f = QtWidgets.QListView(dialog_widget)
            lv_f.setFont(base_font)
            lv_f.setStyleSheet("QListView { background-color: #ffffff; color: #000000; } QListView::item:selected { background: #0078D7; color: #ffffff; }")
            pal_list = lv_f.palette()
            pal_list.setColor(QtGui.QPalette.Base, QtGui.QColor("#ffffff"))
            pal_list.setColor(QtGui.QPalette.Text, QtGui.QColor("#000000"))
            lv_f.setPalette(pal_list)
            cb_filament.setView(lv_f)
        except Exception:
            pass
        cb_filament.addItem("(None)")
        for f in filament_names:
            cb_filament.addItem(f)
        if current.get("filament"):
            idx = cb_filament.findText(current.get("filament"))
            if idx >= 0:
                cb_filament.setCurrentIndex(idx)

        cb_status = QComboBox(dialog_widget)
        cb_status.setFont(base_font)
        try:
            cb_status.setMinimumWidth(220)
        except Exception:
            pass
        try:
            cb_status.setStyleSheet("QComboBox { background-color: #ffffff; color: #000000; } QComboBox QAbstractItemView, QComboBox QListView { background-color: #ffffff; color: #000000; selection-background-color: #0078D7; selection-color: #ffffff; }")
        except Exception:
            pass
        try:
            lv_s = QtWidgets.QListView(dialog_widget)
            lv_s.setFont(base_font)
            lv_s.setStyleSheet("QListView { background-color: #ffffff; color: #000000; } QListView::item:selected { background: #0078D7; color: #ffffff; }")
            pal_list2 = lv_s.palette()
            pal_list2.setColor(QtGui.QPalette.Base, QtGui.QColor("#ffffff"))
            pal_list2.setColor(QtGui.QPalette.Text, QtGui.QColor("#000000"))
            lv_s.setPalette(pal_list2)
            cb_status.setView(lv_s)
        except Exception:
            pass
        for s in getattr(model, 'status_options', ["Empty", "Unknown", "Loaded", "Staged"]):
            cb_status.addItem(s)
        idx = cb_status.findText(current.get("status", "Unknown"))
        if idx >= 0:
            cb_status.setCurrentIndex(idx)

        cb_nozzle = QComboBox(dialog_widget)
        cb_nozzle.setFont(base_font)
        try:
            cb_nozzle.setMinimumWidth(220)
        except Exception:
            pass
        try:
            cb_nozzle.setStyleSheet("QComboBox { background-color: #ffffff; color: #000000; } QComboBox QAbstractItemView, QComboBox QListView { background-color: #ffffff; color: #000000; selection-background-color: #0078D7; selection-color: #ffffff; }")
        except Exception:
            pass
        try:
            lv_n = QtWidgets.QListView(dialog_widget)
            lv_n.setFont(base_font)
            lv_n.setStyleSheet("QListView { background-color: #ffffff; color: #000000; } QListView::item:selected { background: #0078D7; color: #ffffff; }")
            pal_list3 = lv_n.palette()
            pal_list3.setColor(QtGui.QPalette.Base, QtGui.QColor("#ffffff"))
            pal_list3.setColor(QtGui.QPalette.Text, QtGui.QColor("#000000"))
            lv_n.setPalette(pal_list3)
            cb_nozzle.setView(lv_n)
        except Exception:
            pass
        cb_nozzle.addItem("Unknown")
        for n in getattr(model, 'nozzle_options', ["0.25", "0.4", "0.6", "0.8", "1.0"]):
            cb_nozzle.addItem(n)
        idx = cb_nozzle.findText(current.get("nozzle", "Unknown"))
        if idx >= 0:
            cb_nozzle.setCurrentIndex(idx)

        # Create explicit labels so we can enforce the same font size as the dialog
        lab_filament = QLabel("Filament", dialog_widget)
        lab_filament.setFont(base_font)
        lab_status = QLabel("Status", dialog_widget)
        lab_status.setFont(base_font)
        lab_nozzle = QLabel("Nozzle", dialog_widget)
        lab_nozzle.setFont(base_font)

        form.addRow(lab_filament, cb_filament)
        form.addRow(lab_status, cb_status)
        form.addRow(lab_nozzle, cb_nozzle)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog_widget)
        try:
            buttons.setFont(base_font)
            # Set OK/Cancel button fonts to an absolute 14px
            for btn in buttons.buttons():
                f = btn.font()
                try:
                    f.setPixelSize(14)
                except Exception:
                    try:
                        f.setPointSize(14)
                    except Exception:
                        pass
                btn.setFont(f)
        except Exception:
            pass
        form.addRow(buttons)
        buttons.accepted.connect(dialog_widget.accept)
        buttons.rejected.connect(dialog_widget.reject)

        # Center the dialog relative to the parent, similar to SelfCenteringMessageBox
        try:
            dialog_widget.adjustSize()
            frameGm = dialog_widget.frameGeometry()
            centerPoint = self.frameGeometry().center()
            frameGm.moveCenter(centerPoint)
            dialog_widget.move(frameGm.topLeft())
        except Exception:
            pass

        if dialog_widget.exec_() == QDialog.Accepted:
            filament = cb_filament.currentText()
            if filament == "(None)":
                filament = None
            status = cb_status.currentText()
            nozzle = cb_nozzle.currentText()
            try:
                model.update_tool_bay_state(tool, filament=filament, status=status, nozzle=nozzle, persist=True)
            except Exception as e:
                self.logger.error(f"Failed to set tool state: {e}")


