import json
import os
import tempfile
import threading
from contextlib import contextmanager
from utils.logger import get_logger


logger = get_logger(__name__)


PRIMARY_PATH = "/home/pi/.octoprint/.printerPreference"
FALLBACK_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                             ".printerPreference")


DEFAULT_STATE = {
    "version": 1,
    "tools": {
        "tool0": {
            "material_bay_a": {"filament": None, "status": "Unknown", "nozzle": "Unknown"}
        },
        "tool1": {
            "material_bay_x": {"filament": None, "status": "Unknown", "nozzle": "Unknown"}
        },
    },
    # Persistent user preferences (extendable)
    "preferences": {
        "filament_runout_enabled": True,
        "filament_jam_enabled": True,
        "print_compatibility_check_enabled": True,  # Default to enabled
        "print_restore_enabled": True,  # Default to enabled
        "auto_resume_enabled": False,  # Default to disabled
        "firmware_update_check_enabled": True,  # Default to enabled
        "advanced_debugging_enabled": False,  # Default to disabled
    }
    # Note: printer_config section removed - all printer configuration now handled by printer_config_manager
}


class PrinterPreferenceStore:
        """Unified persistence layer for printer runtime state & user preferences.

        Responsibilities:
            * Load (with fallback) and cache a single JSON document.
            * Provide atomic saves (only when dirty) to reduce disk churn.
            * Offer high-level getters/setters for tool bay state and preferences.
            * Provide a batching context manager to coalesce multiple writes.
            * Handle legacy schemas (flat tool state) transparently.
        """

        def __init__(self, primary_path: str = PRIMARY_PATH, fallback_path: str = FALLBACK_PATH):
                self.primary_path = primary_path
                self.fallback_path = fallback_path
                self._cache = None          # in-memory state dict
                self._dirty = False          # pending changes flag
                # NOTE: Use RLock because several public setters acquire the lock
                # and then call load_full(), which itself acquires the same lock.
                # A regular Lock caused a self-deadlock (UI hang) when toggling
                # preferences (e.g., filament runout button) because
                # set_preference -> with _lock -> load_full() -> with _lock.
                self._lock = threading.RLock()
                self._batch_depth = 0        # nested batch tracking

        def _read_json(self, path: str):
            try:
                if not os.path.exists(path):
                    return None
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read printer preferences at {path}: {e}")
                return None

        def _fresh_load(self) -> dict:
            data = self._read_json(self.primary_path)
            if data is None:
                data = self._read_json(self.fallback_path)
            if data is None:
                data = DEFAULT_STATE.copy()
            # Ensure required top-level keys / defaults
            if "tools" not in data:
                data["tools"] = DEFAULT_STATE["tools"].copy()
            prefs = data.get("preferences") or {}
            # Inject defaults if missing
            for k, v in DEFAULT_STATE["preferences"].items():
                prefs.setdefault(k, v)
            data["preferences"] = prefs
            
            # Legacy upgrade: flat tool schema (filament/status/nozzle at tools.toolX root)
            for tool_id in ("tool0", "tool1"):
                raw = data["tools"].get(tool_id)
                if isinstance(raw, dict):
                    if any(k in raw for k in ("filament", "status", "nozzle")):
                        # Wrap into default bay
                        bay = "material_bay_a" if tool_id == "tool0" else "material_bay_x"
                        upgraded = {bay: {
                            "filament": raw.get("filament"),
                            "status": raw.get("status", "Unknown"),
                            "nozzle": raw.get("nozzle", "Unknown"),
                        }}
                        data["tools"][tool_id] = upgraded
            return data

        def load(self) -> dict:
            """Return (uncached) state for compatibility with existing callers."""
            return self._fresh_load()

        def load_full(self) -> dict:
            """Return cached state, loading & upgrading if necessary."""
            with self._lock:
                if self._cache is None:
                    self._cache = self._fresh_load()
                return self._cache

        def _atomic_write(self, dest_path: str, data: dict):
            directory = os.path.dirname(dest_path)
            if not os.path.isdir(directory):
                # Directory must exist for atomic write; let caller choose fallback
                raise FileNotFoundError(f"Directory does not exist: {directory}")

            fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".printerPreference.tmp.")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    json.dump(data, tmp, indent=2)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                # Atomic replace on POSIX and Windows (since Python 3.3)
                os.replace(tmp_path, dest_path)
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

        def save_raw(self, state: dict) -> bool:
            for path in (self.primary_path, self.fallback_path):
                try:
                    self._atomic_write(path, state)
                    logger.info(f"Saved printer preferences to {path}")
                    return True
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.error(f"Failed to save printer preferences at {path}: {e}")
            return False

        def save(self, force: bool = False) -> bool:
            with self._lock:
                if not force and (not self._dirty or self._cache is None):
                    return True
                state = self._cache or DEFAULT_STATE.copy()
            ok = self.save_raw(state)
            if ok:
                with self._lock:
                    self._dirty = False
            return ok

        # --- Batch context ----------------------------------------------------
        @contextmanager
        def batch(self):
            """Group multiple mutations into a single save.

            Example:
                with store.batch():
                    store.set_preference('filament_runout_enabled', True)
                    store.set_tool_state('tool0', filament='PLA')
            """
            with self._lock:
                self._batch_depth += 1
            try:
                yield
            finally:
                with self._lock:
                    self._batch_depth -= 1
                    should_flush = self._batch_depth == 0 and self._dirty
                if should_flush:
                    self.save()

        # --- Preferences API --------------------------------------------------
        def get_preferences(self) -> dict:
            return self.load_full().get("preferences", {})

        def get_preference(self, key: str, default=None):
            return self.get_preferences().get(key, default)

        def set_preference(self, key: str, value) -> None:
            with self._lock:
                prefs = self.load_full().setdefault("preferences", {})
                if prefs.get(key) != value:
                    prefs[key] = value
                    self._dirty = True
                    if self._batch_depth == 0:
                        self.save()

        def update_preferences(self, **kwargs) -> bool:
            with self._lock:
                prefs = self.load_full().setdefault("preferences", {})
                changed = False
                for k, v in kwargs.items():
                    if prefs.get(k) != v:
                        prefs[k] = v
                        changed = True
                if changed:
                    self._dirty = True
                    if self._batch_depth == 0:
                        self.save()
            return True

        # --- Tool state API ---------------------------------------------------
        def get_tool_state(self, tool: str, bay: str = None) -> dict:
            data = self.load_full()
            tools = data.setdefault("tools", {})
            tool_entry = tools.setdefault(tool, {})
            if bay is None and tool in ("tool0", "tool1"):
                bay = "material_bay_a" if tool == "tool0" else "material_bay_x"
            bay_entry = tool_entry.setdefault(bay, {"filament": None, "status": "Unknown", "nozzle": "Unknown"})
            return bay_entry

        def set_tool_state(self, tool: str, bay: str = None, filament=None, status=None, nozzle=None) -> dict:
            with self._lock:
                tools = self.load_full().setdefault("tools", {})
                tool_entry = tools.setdefault(tool, {})
                if bay is None and tool in ("tool0", "tool1"):
                    bay = "material_bay_a" if tool == "tool0" else "material_bay_x"
                cur = tool_entry.setdefault(bay, {"filament": None, "status": "Unknown", "nozzle": "Unknown"}).copy()
                if filament is not None:
                    cur["filament"] = filament
                if status is not None:
                    cur["status"] = status
                if nozzle is not None:
                    cur["nozzle"] = nozzle
                tool_entry[bay] = cur
                self._dirty = True
                if self._batch_depth == 0:
                    self.save()
                return cur

        def list_tool_bays(self, tool: str):
            data = self.load_full()
            return list(data.get("tools", {}).get(tool, {}).keys())

        # Note: All printer configuration now handled by printer_config_manager
        # Use get_current_printer_selection() and related functions from printer_config_manager
