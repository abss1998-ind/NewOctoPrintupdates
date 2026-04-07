# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import os
import subprocess
import sys
import time

from ._version import get_versions
__version__ = get_versions()['version']
del get_versions

# import time
# import subprocess
# from threading import Timer

# class RepeatedTimer(object):
# 	def __init__(self, interval, function, *args, **kwargs):
# 		self._timer = None
# 		self.interval = interval
# 		self.function = function
# 		self.args = args
# 		self.kwargs = kwargs
# 		self.is_running = False
#
# 	def _run(self):
# 		self.is_running = False
# 		self.start()
# 		self.function(*self.args, **self.kwargs)
#
# 	def start(self):
# 		if not self.is_running:
# 			self._timer = Timer(self.interval, self._run)
# 			self._timer.start()
# 			self.is_running = True
#
# 	def stop(self):
# 		if self.is_running:
# 			self._timer.cancel()
# 			self.is_running = False


class ControlCenter(octoprint.plugin.StartupPlugin):
    def on_after_startup(self):
        # self.resetInetrval = int(self._settings.get(["resetInetrval"]))
        self._logger.info("TouchUI Plugin Started")
        
        # Check and update xinit file
        self._check_and_update_xinit_file()
        
        # self._worker = RepeatedTimer(self.resetInetrval, self.worker)
        # self._worker.start()
    
    def _check_and_update_xinit_file(self):
        """Check and update the xinit file with the correct path to main.py"""
        xinit_file = "/etc/X11/xinit/xinitrc"
        
        try:
            # Get the current plugin directory path
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            main_py_path = os.path.join(plugin_dir, "main.py")
            
            # Verify that main.py exists in the plugin directory
            if not os.path.exists(main_py_path):
                self._logger.error(f"main.py not found at expected location: {main_py_path}")
                return
            
            # Expected xinit content - using the detected plugin directory
            expected_content = f"""#!/bin/sh

# /etc/X11/xinit/xinitrc
#
# global xinitrc file, used by all X sessions started by xinit (startx)
cd {plugin_dir}/
sudo chmod +x main.py
sudo python3 main.py
# invoke global X session script
. /etc/X11/Xsession
"""
            
            needs_update = False
            current_content = ""
            
            # Check if xinit file exists and read its content
            try:
                with open(xinit_file, 'r') as f:
                    current_content = f.read()
                    
                # Check if the content contains the correct path to our plugin
                if plugin_dir not in current_content or "octoprint_ControlCenter" not in current_content:
                    needs_update = True
                    self._logger.info(f"xinit file does not contain correct path to {plugin_dir}")
                else:
                    self._logger.info("xinit file already contains correct ControlCenter path")
                    
            except FileNotFoundError:
                needs_update = True
                self._logger.info("xinit file does not exist, will create it")
            except IOError as e:
                self._logger.error(f"Error reading xinit file: {e}")
                return
            
            # Update the file if needed
            if needs_update:
                try:
                    # Write the new content to a temporary file first
                    temp_file = "/tmp/xinitrc_temp"
                    with open(temp_file, 'w') as f:
                        f.write(expected_content)
                    
                    # Use sudo to copy the file to the correct location
                    result = subprocess.run(
                        ["sudo", "cp", temp_file, xinit_file], 
                        check=True, 
                        capture_output=True, 
                        text=True
                    )
                    
                    # Set proper permissions
                    subprocess.run(
                        ["sudo", "chmod", "755", xinit_file], 
                        check=True, 
                        capture_output=True, 
                        text=True
                    )
                    
                    # Clean up temp file
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                    
                    self._logger.info(f"Successfully updated xinit file with ControlCenter path: {plugin_dir}")
                    
                    # Restart the X session with the new xinit configuration
                    self._restart_touch_ui()
                    
                except subprocess.CalledProcessError as e:
                    self._logger.error(f"Failed to update xinit file: {e}")
                    if e.stderr:
                        self._logger.error(f"Command stderr: {e.stderr}")
                    if e.stdout:
                        self._logger.error(f"Command stdout: {e.stdout}")
                except OSError as e:
                    self._logger.error(f"OS error when updating xinit file: {e}")
                except Exception as e:
                    self._logger.error(f"Unexpected error updating xinit file: {e}")
                finally:
                    # Ensure temp file is cleaned up even if there's an error
                    if os.path.exists("/tmp/xinitrc_temp"):
                        try:
                            os.remove("/tmp/xinitrc_temp")
                        except:
                            pass
                    
        except Exception as e:
            self._logger.error(f"Error in _check_and_update_xinit_file: {e}")
            import traceback
            self._logger.error(f"Traceback: {traceback.format_exc()}")
    
    def _restart_touch_ui(self):
        """Restart the touch UI by running sudo startx"""
        try:
            self._logger.info("Restarting touch UI with updated xinit configuration...")
            
            # First, try to kill any existing X sessions
            try:
                # Kill existing X sessions gracefully
                subprocess.run(
                    ["sudo", "pkill", "-f", "startx"], 
                    capture_output=True, 
                    text=True,
                    timeout=10
                )
                self._logger.info("Terminated existing X sessions")
                
                # Give it a moment to clean up
                time.sleep(2)
                
            except subprocess.CalledProcessError:
                # It's okay if there are no existing X sessions to kill
                self._logger.info("No existing X sessions found to terminate")
            except subprocess.TimeoutExpired:
                self._logger.warning("Timeout while trying to terminate X sessions")
            
            # Start the new X session with startx
            # Use Popen to start it in the background since startx is a long-running process
            try:
                self._logger.info("Starting new X session with sudo startx...")
                
                # Start startx in the background
                process = subprocess.Popen(
                    ["sudo", "startx"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                self._logger.info(f"Started touch UI process with PID: {process.pid}")
                
                # Don't wait for the process to complete since startx runs indefinitely
                # Just log that we started it successfully
                
            except Exception as e:
                self._logger.error(f"Failed to start touch UI with startx: {e}")
                
        except Exception as e:
            self._logger.error(f"Error in _restart_touch_ui: {e}")
            import traceback
            self._logger.error(f"Traceback: {traceback.format_exc()}")

    def get_update_information(self):
        return dict(
            ControlCenter=dict(
                displayName="ControlCenter",
                displayVersion=self._plugin_version,
                # version check: github repository
                type="github_release",
                user="FracktalWorks",
                repo="ControlCenter",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/FracktalWorks/ControlCenter/archive/{target_version}.zip"
            )
        )


__plugin_name__ = "ControlCenter"
__plugin_version__ = __version__
__plugin_pythoncompat__ = ">=3,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = ControlCenter()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
