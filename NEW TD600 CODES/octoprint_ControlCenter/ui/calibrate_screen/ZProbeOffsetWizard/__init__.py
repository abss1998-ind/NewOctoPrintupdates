"""
Z Probe Offset Calibration Wizard Module
========================================

Manual probe offset calibration wizard for accurate first layer printing.

This module provides a PyQt5-based wizard for calibrating Z probe offsets using
a combination of automated probe accuracy testing and manual bed movement with
paper feeler gauge technique.

Key Components:
- ZProbeOffsetWizard: Main wizard class with 4-step calibration process
- Video guidance using QMovie for GIF playback
- Timeout handling for robust operation
- M851 probe offset application

Usage:
    from ZProbeOffsetWizard import ZProbeOffsetWizard
    wizard = ZProbeOffsetWizard(main_window)
    wizard.show()
"""

from .ZProbeOffsetWizard import ZProbeOffsetWizard

__all__ = ['ZProbeOffsetWizard']
