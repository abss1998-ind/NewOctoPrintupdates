"""
OctoPrint Singleton Module
Provides a single point of access to the OctoPrint API client for all components
"""

from utils.logger import get_logger
logger = get_logger(__name__)
from octoprint_client.octoprintAPI import octoprintAPI

# Global client instance
_octoprint_client = None

def initialize(ip, api_key):
    """Initialize the OctoPrint client singleton with connection parameters"""
    global _octoprint_client
    
    if _octoprint_client is None:
        logger.info(f"Initializing OctoPrint client for {ip}")
        _octoprint_client = octoprintAPI(ip, api_key)
        logger.info("OctoPrint client initialized successfully")
    else:
        logger.debug("OctoPrint client already initialized")

def get_client():
    """Get the OctoPrint client instance"""
    if _octoprint_client is None:
        logger.error("OctoPrint client accessed before initialization")
        raise RuntimeError("OctoPrint client not initialized. Call initialize() first.")
    
    return _octoprint_client

def reset():
    """Reset the OctoPrint client (for testing purposes)"""
    global _octoprint_client
    _octoprint_client = None
    logger.info("OctoPrint client reset")