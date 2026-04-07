from PyQt5 import QtCore
import subprocess
import time
import re
from utils.logger import get_logger



class ThreadRestartNetworking(QtCore.QThread):
    """Thread to restart network interfaces without blocking the UI"""
    
    WLAN = "wlan0"
    ETH = "eth0"
    
    # Signal emitted with the new IP address, or None if failed
    signal = QtCore.pyqtSignal(object)

    def __init__(self, interface):
        """Initialize the network restart thread"""
        super(ThreadRestartNetworking, self).__init__()
        self.interface = interface
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info(f"Initialized ThreadRestartNetworking for {interface}")
        
    def run(self):
        """Run the network restart process"""
        self.logger.info(f"Restarting network interface: {self.interface}")
        self.restart_interface()
        
        # Try up to 3 times to get an IP address
        attempt = 0
        while attempt < 3:
            ip = self.get_ip()
            if ip:
                self.logger.info(f"Network interface {self.interface} restarted with IP: {ip}")
                self.signal.emit(ip)
                break
            else:
                attempt += 1
                time.sleep(5)
                self.logger.warning(f"No IP address for {self.interface}, attempt {attempt}/3")
        
        # If we tried 3 times and failed, emit None
        if attempt >= 3:
            self.logger.error(f"Failed to get IP address for {self.interface} after 3 attempts")
            self.signal.emit(None)

    def restart_interface(self):
        """Restart the network interface"""
        try:
            if self.interface == self.WLAN:
                # For WiFi, use wpa_cli to reconfigure
                subprocess.call(["wpa_cli", "-i", self.interface, "reconfigure"], shell=False)
                self.logger.info("WiFi interface reconfigured")
            elif self.interface == self.ETH:
                # For Ethernet, cycle the interface
                subprocess.call(["ifconfig", self.interface, "down"], shell=False)
                time.sleep(1)
                subprocess.call(["ifconfig", self.interface, "up"], shell=False)
                self.logger.info("Ethernet interface cycled")
            
            # Give the interface time to come up
            time.sleep(5)
            
        except Exception as e:
            self.logger.error(f"Failed to restart interface {self.interface}: {e}")
            
    def get_ip(self):
        """Get the IP address for this interface"""
        try:
            # Run ifconfig and grep for the interface and its inet addr
            cmd = f"ifconfig {self.interface} | grep 'inet '"
            result = subprocess.check_output(cmd, shell=True).decode('utf-8')
            
            # Extract IP address using a simple split method
            # This assumes the output format is consistent (it is on Raspberry Pi)
            if 'inet ' in result:
                ip = result.split('inet ')[1].split(' ')[0]
                return ip
            return None
        except Exception as e:
            self.logger.error(f"Failed to get IP for {self.interface}: {e}")
            return None



def getIP(interface):
    logger = get_logger(__name__)
    try:
        scan_result = (
            subprocess.Popen(
                "ifconfig | grep " + interface + " -A 1", stdout=subprocess.PIPE, shell=True
            ).communicate()[0]
        ).decode("utf-8")
        rInetAddr = r"inet\s*([\d.]+)"
        rInet6Addr = r"inet6"
        mt6Ip = re.search(rInet6Addr, scan_result)
        mtIp = re.search(rInetAddr, scan_result)
        if not mt6Ip and mtIp and len(mtIp.groups()) == 1:
            return str(mtIp.group(1))
    except Exception as e:
        logger.error("Error in getIP: {}".format(e))
        return None


def getMac(interface):
    logger = get_logger(__name__)
    logger.info("Getting MAC for interface: {}".format(interface))
    try:
        mac = subprocess.Popen(
            " cat /sys/class/net/" + interface + "/address",
            stdout=subprocess.PIPE,
            shell=True,
        ).communicate()[0].rstrip()
        if not mac:
            return "Not found"
        return mac.upper()
    except Exception as e:
        logger.error("Error in getMac: {}".format(e))
        return "Error"


def getWifiAp():
    logger = get_logger(__name__)
    logger.info("Getting Wifi AP")
    try:
        ap = subprocess.Popen(
            "iwgetid -r", stdout=subprocess.PIPE, shell=True
        ).communicate()[0].rstrip()
        if not ap:
            return "Not connected"
        return ap.decode("utf-8")
    except Exception as e:
        logger.error("Error in getWifiAp: {}".format(e))
        return "Error"


def getHostname():
    logger = get_logger(__name__)
    logger.info("Getting Hostname")
    try:
        hostname = subprocess.Popen(
            "cat /etc/hostname", stdout=subprocess.PIPE, shell=True
        ).communicate()[0].rstrip()
        if not hostname:
            return "Not connected"
        return hostname.decode("utf-8") + ".local"
    except Exception as e:
        logger.error("Error in getHostname: {}".format(e))
        return "Error"