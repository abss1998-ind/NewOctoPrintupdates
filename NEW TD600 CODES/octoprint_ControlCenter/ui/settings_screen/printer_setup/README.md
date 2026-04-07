# Printer Setup Settings

This module provides the user interface for configuring printer types in the Control Center application.

## Files

- `printer_setup.py` - Main printer setup widget class
- `printer_setup.ui` - Qt Designer UI file defining the interface layout
- `README.md` - This documentation file

## Features

- Display current active printer configuration
- Dropdown selection of available printer types from firmware folder
- Cancel and Set buttons for applying changes
- Integration with printer configuration storage
- Automatic MCU configuration preservation
- User confirmation dialogs
- **NEW**: Complete OctoPrint configuration restoration
- **NEW**: Automatic printer profile updates with correct build volume and extruder count
- **NEW**: Printer-specific appearance name updates in OctoPrint

## Dependencies

- `utils.printer_config_manager` - Unified configuration manager for both Klipper and OctoPrint configs
- `utils.printer_config_store` - Persistent storage for printer configuration
- `utils.dialog` - Dialog utilities for user interaction

## New Configuration Management

The printer setup now uses the enhanced `PrinterConfigManager` which dynamically extracts all configuration from Klipper firmware files:

1. **Dynamic Configuration Extraction**: All printer settings are read from `PRINTER_VARIABLES` in the firmware files
2. **No Hardcoded Settings**: Printer specifications are extracted in real-time from firmware files
3. **Scalable Architecture**: New printers can be added by simply placing their firmware file in the firmware folder
4. **Klipper Configuration**: Copies all firmware files and updates printer.cfg with the selected printer
5. **OctoPrint Configuration**: 
   - Updates `config.yaml` with the printer name in the appearance section
   - Updates `_default.profile` with correct:
     - Printer name (extracted from firmware filename)
     - Extruder count (from `is_dual_nozzle` variable)
     - Build volume dimensions (from `bed_x_max`, `bed_y_max`, `bed_z_max` variables)
     - Extruder offsets for dual-extruder printers
6. **System Files**: Restores network configurations and user settings

## Configuration Extraction

The system parses each printer's `PRINTER_VARIABLES` macro to extract:
- Build volume from bed size variables
- Extruder count from `is_dual_nozzle` flag
- Calibration positions for bed leveling
- Tool purge positions
- PTFE tube length
- Display names generated from firmware filenames

## Current Auto-Detected Printers

The system automatically detects these printers from the firmware folder:
- **Dragon 400**: 430×400×418mm build volume, single extruder
- **Dragon 500**: 520×420×413mm build volume, single extruder  
- **Twin Dragon 600**: 620×620×414mm build volume, dual extruder
- **Twin Dragon 600X300**: 600×300×422mm build volume, dual extruder

*Note: These configurations are automatically detected from firmware files, not hardcoded.*

## Usage

The printer setup screen is accessed from the main settings menu and allows users to select between different printer configurations. When a printer is selected and applied:

1. All Klipper firmware files are copied to `/home/pi/`
2. `printer.cfg` is updated to include the selected printer configuration
3. OctoPrint configuration files are updated with printer-specific settings
4. User is prompted to restart the system for changes to take effect

This ensures both the 3D printer firmware (Klipper) and the printer management software (OctoPrint) are properly configured for the selected printer type.
