"""
Printer Configuration Manager
Unified utility for managing both Klipper and OctoPrint configuration files, 
printer selection, variable parsing, and backup operations.
"""
import os
import shutil
import glob
import re
import json
import subprocess
import sys
import time
from typing import List, Dict, Optional, Any

try:
    import yaml
except ImportError:
    print("PyYAML not found. Attempting to install...")
    try:
        # Try to install PyYAML automatically
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'PyYAML'])
        import yaml
        print("✓ PyYAML installed successfully!")
    except subprocess.CalledProcessError:
        # If pip install fails, try with sudo
        try:
            subprocess.check_call(['sudo', 'pip', 'install', 'PyYAML'])
            import yaml
            print("✓ PyYAML installed successfully with sudo!")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise ImportError(
                "Failed to automatically install PyYAML. "
                "Please install it manually with: pip install PyYAML or sudo pip install PyYAML"
            ) from e

try:
    from packaging import version
except ImportError:
    print("packaging not found. Attempting to install...")
    try:
        # Try to install packaging automatically
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'packaging'])
        from packaging import version
        print("✓ packaging installed successfully!")
    except subprocess.CalledProcessError:
        # If pip install fails, try with sudo
        try:
            subprocess.check_call(['sudo', 'pip', 'install', 'packaging'])
            from packaging import version
            print("✓ packaging installed successfully with sudo!")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print("Warning: packaging module not available. Version comparison will use string comparison as fallback.")
            version = None

from utils.logger import get_logger

logger = get_logger(__name__)

# Configuration paths
FIRMWARE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firmware")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
PRINTER_CFG_PATH = '/home/pi/printer.cfg'
KLIPPER_CONFIG_PATH = '/home/pi/'
OCTOPRINT_CONFIG_PATH = '/home/pi/.octoprint/'
BACKUP_CFG_PATTERN = '/home/pi/printer-*.cfg'

# Fallback values when configuration cannot be read
FALLBACK_CONFIG = {
    'name': 'Unknown Printer',
    'extruder_count': 1,
    'bed_width': 200,
    'bed_depth': 200,
    'bed_height': 200,
    'is_dual': False
}


class PrinterConfigManager:
    """Unified manager for all printer configuration operations."""
    
    def __init__(self):
        self.firmware_path = FIRMWARE_PATH
        self.config_path = CONFIG_PATH
        self.printer_cfg_path = PRINTER_CFG_PATH
        self.klipper_config_path = KLIPPER_CONFIG_PATH
        self.octoprint_config_path = OCTOPRINT_CONFIG_PATH
        self.backup_pattern = BACKUP_CFG_PATTERN

    # ========================================================================
    # PRINTER DISCOVERY AND MANAGEMENT
    # ========================================================================
    
    def get_available_printers(self) -> List[str]:
        """Get list of available printer configurations from the firmware folder."""
        available_printers = []
        
        try:
            if os.path.exists(self.firmware_path):
                for file in os.listdir(self.firmware_path):
                    if file.startswith("PRINTER_") and file.endswith(".cfg"):
                        printer_name = file[8:-4]  # Remove "PRINTER_" prefix and ".cfg" suffix
                        available_printers.append(printer_name)
                        
                logger.debug(f"Found {len(available_printers)} printer configurations")
            else:
                logger.warning(f"Firmware path not found: {self.firmware_path}")
                
        except Exception as e:
            logger.error(f"Error getting available printers: {e}")
            
        return sorted(available_printers)
    
    def get_printer_display_name(self, printer_name: str) -> str:
        """Convert printer name to display name by extracting from Klipper config."""
        # Try to get name from printer configuration variables
        config_file = os.path.join(self.firmware_path, f"PRINTER_{printer_name}.cfg")
        if os.path.exists(config_file):
            # Extract a reasonable display name from the printer name
            # Convert DRAGON_400 -> Dragon 400, TWINDRAGON_600 -> Twin Dragon 600, etc.
            display_name = printer_name.replace("_", " ").title()
            if display_name.startswith("Twindragon"):
                display_name = display_name.replace("Twindragon", "Twin Dragon")
            return display_name
        
        # Fallback to simple conversion
        return printer_name.replace("_", " ").title()
    
    def get_printer_filename(self, printer_name: str) -> str:
        """Convert printer name back to filename format."""
        return f"PRINTER_{printer_name}.cfg"
    
    def get_firmware_files(self) -> List[str]:
        """Get list of all firmware configuration files."""
        firmware_files = []
        
        try:
            if os.path.exists(self.firmware_path):
                firmware_files = [f for f in os.listdir(self.firmware_path) if f.endswith('.cfg')]
                logger.debug(f"Found {len(firmware_files)} firmware files")
            else:
                logger.warning(f"Firmware path not found: {self.firmware_path}")
                
        except Exception as e:
            logger.error(f"Error getting firmware files: {e}")
            
        return firmware_files

    # ========================================================================
    # PRINTER.CFG PARSING AND MANAGEMENT
    # ========================================================================
    
    def get_current_printer_selection(self) -> Optional[str]:
        """Get the currently active printer configuration from printer.cfg."""
        try:
            if os.path.exists(self.printer_cfg_path):
                with open(self.printer_cfg_path, 'r') as f:
                    content = f.read()
                    
                # Look for active include statements
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('[include PRINTER_') and not line.startswith('#'):
                        match = re.search(r'PRINTER_(\w+)\.cfg', line)
                        if match:
                            return match.group(1)
                            
        except Exception as e:
            logger.error(f"Error getting current printer selection: {e}")
            
        return None

    # ========================================================================
    # PRINTER_VARIABLES PARSING
    # ========================================================================
    
    def parse_printer_variables_from_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse PRINTER_VARIABLES macro from a specific configuration file."""
        try:
            if not os.path.exists(file_path):
                logger.warning(f"File not found: {file_path}")
                return None
                
            with open(file_path, 'r') as f:
                content = f.read()
                
            variables = {}
            in_printer_variables = False
            
            for line in content.split('\n'):
                line = line.strip()
                
                if line.startswith('[gcode_macro PRINTER_VARIABLES]'):
                    in_printer_variables = True
                    continue
                    
                if in_printer_variables:
                    if line.startswith('[') and not line.startswith('[gcode_macro'):
                        break
                        
                    if line.startswith('variable_'):
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            var_name = parts[0].replace('variable_', '').strip()
                            var_value = parts[1].split('#')[0].strip()  # Remove comments
                            variables[var_name] = self._parse_variable_value(var_value)
                            
            return variables if variables else None
            
        except Exception as e:
            logger.error(f"Error parsing PRINTER_VARIABLES from {file_path}: {e}")
            return None
    
    def _parse_variable_value(self, value_str: str) -> Any:
        """Parse a variable value string into its appropriate Python type."""
        value_str = value_str.strip()
        
        # Handle string values (quoted)
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            return value_str[1:-1]
        
        # Handle numeric values first (before boolean check)
        try:
            if '.' in value_str:
                return float(value_str)
            else:
                return int(value_str)
        except ValueError:
            pass
        
        # Handle boolean values (only if not numeric)
        if value_str.lower() == 'true':
            return True
        elif value_str.lower() == 'false':
            return False
        
        # Default to string if we can't parse it
        return value_str
    
    def get_printer_variables_from_active_config(self) -> Optional[Dict[str, Any]]:
        """Get PRINTER_VARIABLES from the currently active printer configuration."""
        current_printer = self.get_current_printer_selection()
        if current_printer:
            # First try the deployed Klipper config directory (where Klipper actually reads from)
            klipper_config_file = os.path.join(self.klipper_config_path, f"PRINTER_{current_printer}.cfg")
            if os.path.exists(klipper_config_file):
                logger.debug(f"Reading PRINTER_VARIABLES from deployed Klipper config: {klipper_config_file}")
                return self.parse_printer_variables_from_file(klipper_config_file)
            
            # Fallback to firmware directory if not deployed yet
            firmware_config_file = os.path.join(self.firmware_path, f"PRINTER_{current_printer}.cfg")
            if os.path.exists(firmware_config_file):
                logger.warning(f"Klipper config not found, falling back to firmware directory: {firmware_config_file}")
                return self.parse_printer_variables_from_file(firmware_config_file)
            
            logger.error(f"Could not find PRINTER_{current_printer}.cfg in either Klipper config or firmware directories")
        return None

    def get_printer_config_from_variables(self, printer_name: str) -> Dict[str, Any]:
        """Get printer configuration by parsing PRINTER_VARIABLES from the printer config file."""
        # First try the deployed Klipper config directory (where Klipper actually reads from)
        klipper_config_file = os.path.join(self.klipper_config_path, f"PRINTER_{printer_name}.cfg")
        firmware_config_file = os.path.join(self.firmware_path, f"PRINTER_{printer_name}.cfg")
        
        variables = None
        config_source = None
        
        # Try Klipper config directory first
        if os.path.exists(klipper_config_file):
            variables = self.parse_printer_variables_from_file(klipper_config_file)
            config_source = "deployed Klipper config"
        
        # Fallback to firmware directory
        if not variables and os.path.exists(firmware_config_file):
            variables = self.parse_printer_variables_from_file(firmware_config_file)
            config_source = "firmware directory"
        
        if not variables:
            logger.warning(f"No PRINTER_VARIABLES found for {printer_name}, using fallback config")
            return FALLBACK_CONFIG.copy()
        
        logger.debug(f"Loaded {printer_name} configuration from {config_source}")
        
        # Extract configuration from variables
        config = {
            'name': self.get_printer_display_name(printer_name),
            'bed_width': variables.get('bed_x_max', FALLBACK_CONFIG['bed_width']) - variables.get('bed_x_min', 0),
            'bed_depth': variables.get('bed_y_max', FALLBACK_CONFIG['bed_depth']) - variables.get('bed_y_min', 0),
            'bed_height': variables.get('bed_z_max', FALLBACK_CONFIG['bed_height']) - variables.get('bed_z_min', 0),
            'is_dual': bool(variables.get('is_dual_nozzle', 0)),
            'extruder_count': 2 if bool(variables.get('is_dual_nozzle', 0)) else 1,
            # Store raw variables for further use
            'variables': variables
        }
        
        logger.debug(f"Extracted config for {printer_name}: {config}")
        return config

    # ========================================================================
    # CONFIGURATION EXTRACTION AND TRANSFORMATION
    # ========================================================================
    
    def extract_printer_configuration(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Extract configuration from PRINTER_VARIABLES in the format expected by config.py."""
        if not variables:
            return {}
            
        config = {
            # Bed size information
            'bed_size': {
                'x_min': variables.get('bed_x_min', 0),
                'x_max': variables.get('bed_x_max', 200),
                'y_min': variables.get('bed_y_min', 0),
                'y_max': variables.get('bed_y_max', 200),
                'z_min': variables.get('bed_z_min', 0),
                'z_max': variables.get('bed_z_max', 200),
            },
            'is_dual_nozzle': bool(variables.get('is_dual_nozzle', 0)),
            'has_chamber_cooling': 'fan1' in variables,
            
            # Machine build size (compatible with config.py format)
            'machineBuildSize': {
                'X': variables.get('bed_x_max', 200) - variables.get('bed_x_min', 0),
                'Y': variables.get('bed_y_max', 200) - variables.get('bed_y_min', 0),
                'Z': variables.get('bed_z_max', 200) - variables.get('bed_z_min', 0),
            },
            
            # Calibration positions
            'calibrationPosition': {
                'X1': variables.get('bed_calibration_x1', 50),
                'Y1': variables.get('bed_calibration_y1', 50),
                'X2': variables.get('bed_calibration_x2', 150),
                'Y2': variables.get('bed_calibration_y2', 50),
                'X3': variables.get('bed_calibration_x3', 100),
                'Y3': variables.get('bed_calibration_y3', 150),
                'X4': variables.get('bed_calibration_x4', 100),
                'Y4': variables.get('bed_calibration_y4', 100),
            },
            
            # Tool positions
            'tool0PurgePosition': {
                'X': variables.get('tool0_pause_position_x', -30),
                'Y': variables.get('tool0_pause_position_y', -77),
            },
            'tool1PurgePosition': {
                'X': variables.get('tool1_pause_position_x', 655),
                'Y': variables.get('tool1_pause_position_y', -77),
            },
            
            # Other settings
            'ptfeTubeLength': variables.get('ptfe_tube_length', 1500),
            'IS_DUAL_NOZZLE': bool(variables.get('is_dual_nozzle', 0)),
        }
        
        # Calculate bed dimensions for backwards compatibility
        config['bed_width'] = config['machineBuildSize']['X']
        config['bed_depth'] = config['machineBuildSize']['Y']
        config['bed_height'] = config['machineBuildSize']['Z']
        
        return config
    
    def get_printer_config_from_klipper(self) -> Optional[Dict[str, Any]]:
        """Get complete printer configuration from active Klipper config."""
        variables = self.get_printer_variables_from_active_config()
        if variables:
            return self.extract_printer_configuration(variables)
        return None

    # ========================================================================
    # OCTOPRINT CONFIGURATION MANAGEMENT
    # ========================================================================
    
    def update_octoprint_config(self, printer_name: str) -> bool:
        """Update OctoPrint config.yaml with printer-specific settings."""
        try:
            source_config = os.path.join(self.config_path, 'config.yaml')
            dest_config = os.path.join(self.octoprint_config_path, 'config.yaml')
            
            if not os.path.exists(source_config):
                logger.error(f"Source config not found: {source_config}")
                return False
                
            # Load the template config
            with open(source_config, 'r') as f:
                config_data = yaml.safe_load(f)
                
            # Update appearance name with current printer
            if 'appearance' not in config_data:
                config_data['appearance'] = {}
                
            config_data['appearance']['name'] = self.get_printer_display_name(printer_name)
            
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(dest_config), exist_ok=True)
            
            # Write updated config
            with open(dest_config, 'w') as f:
                yaml.safe_dump(config_data, f, default_flow_style=False)
                
            logger.info(f"Updated OctoPrint config with printer: {printer_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating OctoPrint config: {e}")
            return False
    
    def update_octoprint_printer_profile(self, printer_name: str) -> bool:
        """Update OctoPrint printer profile with printer-specific settings."""
        try:
            source_profile = os.path.join(self.config_path, '_default.profile')
            dest_profile = os.path.join(self.octoprint_config_path, 'printerProfiles', '_default.profile')
            
            if not os.path.exists(source_profile):
                logger.error(f"Source profile not found: {source_profile}")
                return False
                
            # Load the template profile
            with open(source_profile, 'r') as f:
                profile_data = yaml.safe_load(f)
                
            # Get printer configuration from Klipper variables
            printer_config = self.get_printer_config_from_variables(printer_name)
            
            # Update profile with dynamic configuration
            profile_data['name'] = printer_config['name']
            profile_data['extruder']['count'] = printer_config['extruder_count']
            profile_data['volume']['width'] = float(printer_config['bed_width'])
            profile_data['volume']['depth'] = float(printer_config['bed_depth'])
            profile_data['volume']['height'] = float(printer_config['bed_height'])
            
            # Update offsets for dual extruder
            if printer_config['extruder_count'] == 2:
                profile_data['extruder']['offsets'] = [
                    [0.0, 0.0],
                    [0.0, 0.0]
                ]
            else:
                profile_data['extruder']['offsets'] = [
                    [0.0, 0.0]
                ]
                    
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(dest_profile), exist_ok=True)
            
            # Write updated profile
            with open(dest_profile, 'w') as f:
                yaml.safe_dump(profile_data, f, default_flow_style=False)
                
            logger.info(f"Updated OctoPrint printer profile for: {printer_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating OctoPrint printer profile: {e}")
            return False
    
    def restore_octoprint_configs(self, printer_name: str) -> bool:
        """Restore all OctoPrint configuration files for the selected printer."""
        try:
            success = True
            
            # Copy basic config files
            config_files = [
                ('users.yaml', 'users.yaml'),
                ('dhcpcd.conf', '/etc/dhcpcd.conf')
            ]
            
            for source_file, dest_path in config_files:
                source = os.path.join(self.config_path, source_file)
                if os.path.exists(source):
                    try:
                        if dest_path.startswith('/etc/'):
                            # System files need sudo
                            os.system(f'sudo cp -f "{source}" "{dest_path}"')
                        else:
                            # OctoPrint files
                            dest = os.path.join(self.octoprint_config_path, dest_path)
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.copy2(source, dest)
                        logger.debug(f"Copied {source_file} to {dest_path}")
                    except Exception as e:
                        logger.error(f"Error copying {source_file}: {e}")
                        success = False
                        
            # Update printer-specific configs
            if not self.update_octoprint_config(printer_name):
                success = False
                
            if not self.update_octoprint_printer_profile(printer_name):
                success = False
                
            # Clean up old files and create default gcode scripts
            try:
                os.system('sudo rm -rf /home/pi/.octoprint/scripts/gcode')
                os.system('sudo rm -rf /home/pi/.octoprint/print_restore.json')
                
                # Create gcode scripts directory
                gcode_scripts_dir = '/home/pi/.octoprint/scripts/gcode'
                os.makedirs(gcode_scripts_dir, exist_ok=True)
                # Set proper ownership for the directory
                os.system(f'sudo chown -R pi:pi "{os.path.dirname(gcode_scripts_dir)}"')
                
                # Create default gcode script files to override existing ones
                default_scripts = {
                    'beforePrintStarted': 'M514 S1  ; Open door/chamber on print start',
                    'beforePrintResumed': 'RESUME\nM514 S1  ; Resume print and open door/chamber',
                    'afterPrintPaused': 'PAUSE\nM514 S0  ; Pause print and close door/chamber',
                    'afterPrintDone': 'G28  ; Home all axes\nM107  ; Turn off part cooling fan\nM104 T0 S0  ; Cool down tool0 nozzle\nM104 T1 S0  ; Cool down tool1 nozzle\nM140 S0  ; Cool down bed\nM84  ; Disable motors\nM514 S0  ; Close door/chamber',
                    'afterPrintCancelled': 'G28  ; Home all axes\nM107  ; Turn off part cooling fan\nM104 T0 S0  ; Cool down tool0 nozzle\nM104 T1 S0  ; Cool down tool1 nozzle\nM140 S0  ; Cool down bed\nM84  ; Disable motors\nM514 S0  ; Close door/chamber'
                }
                
                for script_name, script_content in default_scripts.items():
                    script_path = os.path.join(gcode_scripts_dir, script_name)
                    try:
                        with open(script_path, 'w') as f:
                            f.write(script_content)
                        # Set proper ownership for the script file
                        os.system(f'sudo chown pi:pi "{script_path}"')
                        logger.debug(f"Created default gcode script: {script_name}")
                    except Exception as e:
                        logger.error(f"Error creating gcode script {script_name}: {e}")
                        success = False
                        
            except Exception as e:
                logger.warning(f"Error cleaning up old files and creating gcode scripts: {e}")
                success = False
                
            return success
            
        except Exception as e:
            logger.error(f"Error restoring OctoPrint configs: {e}")
            return False

    # ========================================================================
    # FILE DEPLOYMENT AND MANAGEMENT
    # ========================================================================
    
    def update_printer_cfg(self, source_path: str, dest_path: str, selected_printer: str, preserve_mcu: bool = True) -> bool:
        """Update printer.cfg with new printer selection while preserving MCU config and SAVE_CONFIG sections."""
        try:
            if not os.path.exists(source_path):
                logger.error(f"Source file not found: {source_path}")
                return False
                
            # Read the template
            with open(source_path, 'r') as f:
                template_content = f.read()
                
            # If preserve_mcu is True and destination file exists, extract MCU config from current file
            existing_mcu_section = ""
            existing_save_config_section = ""
            
            if preserve_mcu and os.path.exists(dest_path):
                logger.info(f"Attempting to preserve MCU config from existing file: {dest_path}")
                try:
                    with open(dest_path, 'r') as f:
                        existing_content = f.read()
                    
                    # Extract MCU Config section
                    mcu_start_marker = "########################################\n# MCU Config\n########################################"
                    save_config_marker = "#*# <---------------------- SAVE_CONFIG ---------------------->"
                    
                    logger.debug(f"Looking for MCU marker in existing file...")
                    logger.debug(f"MCU marker found: {mcu_start_marker in existing_content}")
                    logger.debug(f"SAVE_CONFIG marker found: {save_config_marker in existing_content}")
                    
                    if mcu_start_marker in existing_content:
                        mcu_start = existing_content.find(mcu_start_marker)
                        logger.debug(f"MCU marker position: {mcu_start}")
                        
                        if save_config_marker in existing_content:
                            save_config_start = existing_content.find(save_config_marker)
                            logger.debug(f"SAVE_CONFIG marker position: {save_config_start}")
                            
                            if mcu_start != -1 and save_config_start != -1 and mcu_start < save_config_start:
                                # Extract MCU section (from MCU Config marker to just before SAVE_CONFIG marker)
                                existing_mcu_section = existing_content[mcu_start:save_config_start].rstrip()
                                logger.info(f"Preserved MCU config section ({len(existing_mcu_section)} chars)")
                            else:
                                # If SAVE_CONFIG comes before MCU (unusual), extract MCU to end
                                existing_mcu_section = existing_content[mcu_start:].rstrip()
                                logger.warning("SAVE_CONFIG found before MCU marker, extracting MCU to end of file")
                        else:
                            # No SAVE_CONFIG marker, extract MCU section to end of file
                            existing_mcu_section = existing_content[mcu_start:].rstrip()
                            logger.info(f"No SAVE_CONFIG found, preserved MCU config to end ({len(existing_mcu_section)} chars)")
                            
                        # Extract SAVE_CONFIG section separately (everything from SAVE_CONFIG marker to end)
                        if save_config_marker in existing_content:
                            save_config_start = existing_content.find(save_config_marker)
                            if save_config_start != -1:
                                existing_save_config_section = existing_content[save_config_start:].rstrip()
                                logger.info(f"Preserved SAVE_CONFIG section ({len(existing_save_config_section)} chars)")
                    else:
                        logger.warning("MCU Config marker not found in existing file")
                    
                except Exception as e:
                    logger.warning(f"Could not extract existing MCU config and SAVE_CONFIG: {e}")
                    # Continue without preserving sections
                    existing_mcu_section = ""
                    existing_save_config_section = ""
            else:
                if not preserve_mcu:
                    logger.info("MCU and SAVE_CONFIG preservation disabled")
                else:
                    logger.info(f"Destination file does not exist: {dest_path}")
            
            # Update the include statement to point to the selected printer
            template_lines = template_content.split('\n')
            updated_lines = []
            
            # Process template content, updating printer includes
            for line in template_lines:
                if 'PRINTER_' in line and '.cfg' in line:
                    if line.strip().startswith('#'):
                        # This is a commented printer config
                        if f'PRINTER_{selected_printer}.cfg' in line:
                            # Uncomment this line and remove any leading spaces after #
                            uncommented = line.replace('#', '', 1).lstrip()
                            updated_lines.append(uncommented)
                        else:
                            # Keep other printer configs commented
                            updated_lines.append(line)
                    else:
                        # This is an active include, comment it out unless it's our target
                        if f'PRINTER_{selected_printer}.cfg' in line:
                            updated_lines.append(line)
                        else:
                            updated_lines.append('#' + line)
                else:
                    updated_lines.append(line)
            
            # Reconstruct the final content
            final_content = '\n'.join(updated_lines)
            
            # If we have preserved sections, replace the template sections with the existing ones
            if existing_mcu_section or existing_save_config_section:
                logger.info("Replacing template sections with preserved ones")
                mcu_start_marker = "########################################\n# MCU Config\n########################################"
                save_config_marker = "#*# <---------------------- SAVE_CONFIG ---------------------->"
                
                if existing_mcu_section and mcu_start_marker in final_content:
                    mcu_start = final_content.find(mcu_start_marker)
                    logger.debug(f"MCU marker position in template: {mcu_start}")
                    
                    if save_config_marker in final_content:
                        # Template has both MCU and SAVE_CONFIG sections
                        # Replace everything from MCU marker to end with preserved sections
                        final_content = final_content[:mcu_start] + existing_mcu_section
                        
                        # Add preserved SAVE_CONFIG if we have it
                        if existing_save_config_section:
                            final_content += "\n\n" + existing_save_config_section
                        logger.info("Replaced template MCU and SAVE_CONFIG with preserved sections")
                    else:
                        # Template has MCU but no SAVE_CONFIG
                        # Replace from MCU marker to end with preserved MCU
                        final_content = final_content[:mcu_start] + existing_mcu_section
                        
                        # Append preserved SAVE_CONFIG if we have it
                        if existing_save_config_section:
                            final_content += "\n\n" + existing_save_config_section
                        logger.info("Replaced template MCU and appended preserved SAVE_CONFIG")
                        
                elif existing_save_config_section:
                    # We only have SAVE_CONFIG to preserve (no MCU section to preserve)
                    if save_config_marker in final_content:
                        # Replace template SAVE_CONFIG with preserved one
                        save_config_start = final_content.find(save_config_marker)
                        final_content = final_content[:save_config_start] + existing_save_config_section
                        logger.info("Replaced template SAVE_CONFIG with preserved section")
                    else:
                        # No SAVE_CONFIG in template, append preserved one
                        final_content += "\n\n" + existing_save_config_section
                        logger.info("Appended preserved SAVE_CONFIG section")
            
            # If we only have SAVE_CONFIG section preserved and it's not already included, append it
            elif existing_save_config_section and "#*# <---------------------- SAVE_CONFIG ---------------------->" not in final_content:
                final_content += "\n\n" + existing_save_config_section
                logger.info("Appended preserved SAVE_CONFIG section")
                    
            # Write the updated content
            with open(dest_path, 'w') as f:
                f.write(final_content)
                
            # Log success with details about what was preserved
            preserved_sections = []
            if existing_mcu_section:
                preserved_sections.append("MCU configuration")
            if existing_save_config_section:
                preserved_sections.append("SAVE_CONFIG calibration data")
                
            if preserved_sections:
                logger.info(f"Updated printer.cfg for {selected_printer} while preserving: {', '.join(preserved_sections)}")
            else:
                logger.info(f"Updated printer.cfg for {selected_printer}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating printer.cfg: {e}")
            return False
    
    def copy_firmware_files(self, selected_printer: str) -> bool:
        """Copy all firmware files and update printer selection."""
        try:
            if not os.path.exists(self.firmware_path):
                logger.error(f"Firmware path not found: {self.firmware_path}")
                return False
                
            # Copy all .cfg files to Klipper config directory (excluding printer.cfg which needs special handling)
            firmware_files = self.get_firmware_files()
            for file in firmware_files:
                if file == 'printer.cfg':
                    # Skip printer.cfg - it will be handled separately with MCU preservation
                    logger.debug(f"Skipping {file} - will be handled with MCU preservation")
                    continue
                    
                source = os.path.join(self.firmware_path, file)
                dest = os.path.join(self.klipper_config_path, file)
                try:
                    shutil.copy2(source, dest)
                    logger.debug(f"Copied {file} to Klipper config")
                except Exception as e:
                    logger.error(f"Error copying {file}: {e}")
                    return False
                    
            # Update printer.cfg with the selected printer (with MCU preservation)
            source_printer_cfg = os.path.join(self.firmware_path, 'printer.cfg')
            dest_printer_cfg = self.printer_cfg_path
            
            if not self.update_printer_cfg(source_printer_cfg, dest_printer_cfg, selected_printer):
                return False
                
            # Update OctoPrint configurations
            if not self.restore_octoprint_configs(selected_printer):
                logger.warning("Failed to update OctoPrint configs, but Klipper config was successful")
                
            logger.info(f"Successfully configured printer: {selected_printer}")
            return True
            
        except Exception as e:
            logger.error(f"Error copying firmware files: {e}")
            return False

    # ========================================================================
    # BACKUP AND RECOVERY OPERATIONS
    # ========================================================================
    
    def is_config_valid(self, config_path: str = None) -> bool:
        """Check if configuration file is valid."""
        if config_path is None:
            config_path = self.printer_cfg_path
            
        try:
            # Basic checks: file exists and has content
            if not os.path.exists(config_path) or os.path.getsize(config_path) == 0:
                return False
            
            # Additional validation for Klipper config files
            return self._validate_klipper_config_structure(config_path)
            
        except Exception as e:
            logger.error(f"Error checking config validity: {e}")
            return False
    
    def _validate_klipper_config_structure(self, config_path: str) -> bool:
        """Validate basic Klipper configuration file structure.
        
        Args:
            config_path: Path to the configuration file to validate
            
        Returns:
            True if the config has basic valid structure, False otherwise
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for basic Klipper config structure
            # At minimum, a valid config should have some section headers [xxx]
            has_sections = '[' in content and ']' in content
            
            # Check it's not just whitespace or comments
            non_comment_lines = [line.strip() for line in content.split('\n') 
                               if line.strip() and not line.strip().startswith('#')]
            has_content = len(non_comment_lines) > 0
            
            # Check for common Klipper corruption indicators
            has_null_bytes = '\x00' in content
            has_binary_data = any(ord(char) > 127 for char in content[:1000])  # Check first 1KB
            
            is_valid = has_sections and has_content and not has_null_bytes and not has_binary_data
            
            if not is_valid:
                logger.debug(f"Config validation failed for {config_path}: "
                           f"has_sections={has_sections}, has_content={has_content}, "
                           f"has_null_bytes={has_null_bytes}, has_binary_data={has_binary_data}")
            
            return is_valid
            
        except Exception as e:
            logger.warning(f"Error validating config structure for {config_path}: {e}")
            return False
    
    def get_backup_files(self, pattern: str = None) -> List[str]:
        """Get list of backup configuration files."""
        if pattern is None:
            pattern = self.backup_pattern
            
        try:
            return sorted(glob.glob(pattern), reverse=True)
        except Exception as e:
            logger.error(f"Error getting backup files: {e}")
            return []
    
    def get_valid_backup_files(self, pattern: str = None) -> List[str]:
        """Get list of valid backup configuration files.
        
        This method checks each backup file for validity and returns only
        the valid ones, sorted by date (newest first).
        
        Args:
            pattern: Glob pattern for backup files. If None, uses default backup pattern.
            
        Returns:
            List of paths to valid backup files, sorted newest first
        """
        if pattern is None:
            pattern = self.backup_pattern
            
        try:
            all_backups = self.get_backup_files(pattern)
            valid_backups = []
            
            for backup_file in all_backups:
                if self.is_config_valid(backup_file):
                    valid_backups.append(backup_file)
                else:
                    logger.debug(f"Invalid backup file skipped: {backup_file}")
            
            logger.info(f"Found {len(valid_backups)} valid backup files out of {len(all_backups)} total")
            return valid_backups
            
        except Exception as e:
            logger.error(f"Error getting valid backup files: {e}")
            return []
    
    def restore_backup_config(self, config_path: str = None, backup_pattern: str = None) -> bool:
        """Restore configuration from the most recent valid backup.
        
        This method iterates through backup files (sorted by date, newest first)
        and restores from the first valid backup found. This ensures that if
        recent backups are corrupted, older valid backups can still be used.
        """
        if config_path is None:
            config_path = self.printer_cfg_path
        if backup_pattern is None:
            backup_pattern = self.backup_pattern
            
        try:
            backups = self.get_backup_files(backup_pattern)
            if not backups:
                logger.warning("No backup files found")
                return False
            
            logger.info(f"Found {len(backups)} backup files, checking for validity...")
            
            # Iterate through backups to find the latest valid one
            for i, backup_file in enumerate(backups):
                logger.debug(f"Checking backup {i+1}/{len(backups)}: {backup_file}")
                
                # Validate the backup file
                if self.is_config_valid(backup_file):
                    logger.info(f"Found valid backup: {backup_file}")
                    try:
                        # Create a backup of current config before restoring (if it exists)
                        if os.path.exists(config_path):
                            backup_current = f"{config_path}.pre-restore-{int(time.time())}"
                            shutil.copy2(config_path, backup_current)
                            logger.debug(f"Backed up current config to: {backup_current}")
                        
                        # Restore from the valid backup
                        shutil.copy2(backup_file, config_path)
                        logger.info(f"Successfully restored config from backup: {backup_file}")
                        
                        # Verify the restoration was successful
                        if self.is_config_valid(config_path):
                            logger.info("Backup restoration completed and verified")
                            return True
                        else:
                            logger.error("Restored config is invalid, restoration failed")
                            return False
                            
                    except Exception as e:
                        logger.error(f"Error restoring from backup {backup_file}: {e}")
                        continue
                else:
                    logger.warning(f"Backup file is invalid: {backup_file}")
                    
            # If we get here, no valid backup was found
            logger.error("No valid backup files found for restoration")
            return False
            
        except Exception as e:
            logger.error(f"Error in backup restoration process: {e}")
            return False
    
    def cleanup_old_backups(self, keep: int = 5, backup_pattern: str = None) -> None:
        """Remove old backup files, keeping only the specified number."""
        if backup_pattern is None:
            backup_pattern = self.backup_pattern
            
        try:
            backups = self.get_backup_files(backup_pattern)
            if len(backups) > keep:
                for backup in backups[keep:]:
                    os.remove(backup)
                    logger.debug(f"Removed old backup: {backup}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up backups: {e}")
    
    def check_klipper_config_files(self) -> Dict[str, bool]:
        """Check if all required Klipper configuration files exist."""
        required_files = [
            'printer.cfg',
            'CORE_GCODE_MACROS.cfg',
            'variables.cfg'
        ]
        
        status = {}
        for file in required_files:
            file_path = os.path.join(self.klipper_config_path, file)
            status[file] = os.path.exists(file_path)
            
        return status
    
    def get_missing_config_files(self) -> List[str]:
        """Get list of missing configuration files."""
        status = self.check_klipper_config_files()
        return [file for file, exists in status.items() if not exists]

    # ========================================================================
    # VERSION CHECKING AND FIRMWARE UPDATE MANAGEMENT
    # ========================================================================
    
    def get_config_version(self, config_path: str) -> Optional[str]:
        """Extract version number from a printer.cfg file.
        
        Args:
            config_path: Path to the printer.cfg file
            
        Returns:
            Version number as string, or None if not found/invalid
        """
        try:
            if not os.path.exists(config_path):
                logger.warning(f"Config file not found: {config_path}")
                return None
                
            with open(config_path, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    line = line.strip()
                    if line.startswith('# Version:'):
                        # Extract version number from "# Version: 2.1" or "# Version: 2.2.2"
                        try:
                            version_str = line.split(':')[1].strip()
                            # Validate that it's a reasonable version format
                            if re.match(r'^\d+(\.\d+)*$', version_str):
                                logger.debug(f"Found version {version_str} in {config_path}")
                                return version_str
                            else:
                                logger.warning(f"Invalid version format at line {line_num} in {config_path}: {line} - version must be numeric (e.g., '2', '2.1', '2.2.2')")
                                return None
                        except (IndexError, ValueError) as e:
                            logger.warning(f"Invalid version format at line {line_num} in {config_path}: {line} - {e}")
                            return None
                            
            logger.debug(f"No version found in {config_path}")
            return None
            
        except Exception as e:
            logger.error(f"Error reading config version from {config_path}: {e}")
            return None
    
    def get_current_config_version(self) -> Optional[str]:
        """Get version of currently active printer.cfg."""
        return self.get_config_version(self.printer_cfg_path)
    
    def get_firmware_config_version(self) -> Optional[str]:
        """Get version of firmware template printer.cfg."""
        firmware_config_path = os.path.join(self.firmware_path, "printer.cfg")
        return self.get_config_version(firmware_config_path)
    
    def is_firmware_update_available(self) -> bool:
        """Check if firmware template has a newer version than current config.
        
        Returns:
            True if firmware version is newer than current version
        """
        try:
            current_version = self.get_current_config_version()
            firmware_version = self.get_firmware_config_version()
            
            # If either version is missing, assume no update needed
            if current_version is None or firmware_version is None:
                logger.debug(f"Version check skipped - current: {current_version}, firmware: {firmware_version}")
                return False
            
            # Use packaging.version for proper semantic version comparison
            if version is not None:
                try:
                    current_ver = version.Version(current_version)
                    firmware_ver = version.Version(firmware_version)
                    is_newer = firmware_ver > current_ver
                except Exception as e:
                    logger.warning(f"Error parsing versions with packaging module: {e}. Falling back to string comparison.")
                    # Fallback to string comparison (works for simple cases like "2.1" vs "2.0")
                    is_newer = self._compare_version_strings(firmware_version, current_version)
            else:
                # Fallback to string comparison when packaging module is not available
                is_newer = self._compare_version_strings(firmware_version, current_version)
            
            if is_newer:
                logger.info(f"Firmware update available: current version {current_version}, firmware version {firmware_version}")
            else:
                logger.debug(f"Firmware up to date: current version {current_version}, firmware version {firmware_version}")
                
            return is_newer
            
        except Exception as e:
            logger.error(f"Error checking firmware update availability: {e}")
            return False
    
    def _compare_version_strings(self, version1: str, version2: str) -> bool:
        """Compare two version strings using basic semantic version logic.
        
        Args:
            version1: First version string (e.g., "2.1" or "2.2.2")
            version2: Second version string (e.g., "2.0" or "2.1.1")
            
        Returns:
            True if version1 is greater than version2
        """
        try:
            # Split versions into components and pad with zeros if needed
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]
            
            # Pad shorter version with zeros
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))
            
            # Compare component by component
            for i in range(max_len):
                if v1_parts[i] > v2_parts[i]:
                    return True
                elif v1_parts[i] < v2_parts[i]:
                    return False
            
            # Versions are equal
            return False
            
        except Exception as e:
            logger.error(f"Error comparing version strings {version1} and {version2}: {e}")
            # Fallback to simple string comparison
            return version1 > version2


# ============================================================================
# SINGLETON INSTANCE AND CONVENIENCE FUNCTIONS
# ============================================================================

# Create singleton instance
_printer_config_manager = None

def get_printer_config_manager() -> PrinterConfigManager:
    """Get singleton instance of PrinterConfigManager."""
    global _printer_config_manager
    if _printer_config_manager is None:
        _printer_config_manager = PrinterConfigManager()
    return _printer_config_manager


# Convenience functions for backwards compatibility
def get_available_printers() -> List[str]:
    """Get list of available printer configurations."""
    return get_printer_config_manager().get_available_printers()

def get_printer_display_name(printer_name: str) -> str:
    """Convert printer name to display name."""
    return get_printer_config_manager().get_printer_display_name(printer_name)

def get_printer_filename(printer_name: str) -> str:
    """Convert printer name back to filename format."""
    return get_printer_config_manager().get_printer_filename(printer_name)

def get_current_printer_selection() -> Optional[str]:
    """Get the currently active printer configuration."""
    return get_printer_config_manager().get_current_printer_selection()

def copy_firmware_files(selected_printer: str) -> bool:
    """Copy all firmware files and update printer selection."""
    return get_printer_config_manager().copy_firmware_files(selected_printer)

def get_printer_config_from_klipper() -> Optional[Dict[str, Any]]:
    """Get complete printer configuration from active Klipper config."""
    return get_printer_config_manager().get_printer_config_from_klipper()

def parse_printer_variables_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Parse PRINTER_VARIABLES from a specific file."""
    return get_printer_config_manager().parse_printer_variables_from_file(file_path)

def extract_printer_configuration(variables: Dict[str, Any]) -> Dict[str, Any]:
    """Extract configuration from PRINTER_VARIABLES."""
    return get_printer_config_manager().extract_printer_configuration(variables)

def restore_octoprint_configs(printer_name: str) -> bool:
    """Restore all OctoPrint configuration files for the selected printer."""
    return get_printer_config_manager().restore_octoprint_configs(printer_name)

def is_firmware_update_available() -> bool:
    """Check if firmware template has a newer version than current config."""
    return get_printer_config_manager().is_firmware_update_available()

def get_current_config_version() -> Optional[str]:
    """Get version of currently active printer.cfg."""
    return get_printer_config_manager().get_current_config_version()

def get_firmware_config_version() -> Optional[str]:
    """Get version of firmware template printer.cfg."""
    return get_printer_config_manager().get_firmware_config_version()

def get_valid_backup_files(pattern: str = None) -> List[str]:
    """Get list of valid backup configuration files."""
    return get_printer_config_manager().get_valid_backup_files(pattern)

def restore_backup_config(config_path: str = None, backup_pattern: str = None) -> bool:
    """Restore configuration from the most recent valid backup."""
    return get_printer_config_manager().restore_backup_config(config_path, backup_pattern)
