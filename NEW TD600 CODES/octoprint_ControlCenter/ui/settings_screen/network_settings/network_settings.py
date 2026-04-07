import os
import subprocess
from PyQt5 import QtGui, QtCore
from PyQt5 import uic
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QLabel, QCheckBox, QComboBox
from functools import partial  # Add missing import for partial function
from utils.custom_widgets import ClickableLineEdit
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import styles  # Import styles module
from utils.keyboard import keyboard  # Import keyboard module

# Network utils import
from utils.network_utils import getIP, getHostname, getWifiAp, getMac
from utils.network_utils import ThreadRestartNetworking

from utils import dialog

from utils.helpers import run_async
from utils.qrcode_image import Image
import time
import subprocess
import qrcode
import io
import re

logger = get_logger(__name__)

# Use centralized logger
class NetworkSettings(QWidget):
    """
    Network Settings widget that allows users to configure network connections
    including WiFi and Static IP settings.
    """

    def __init__(self, parent, settings_screen):
        super(NetworkSettings, self).__init__(parent)
        self.mainSettingsWidget = settings_screen  # Reference to the main settings widget
        self.logger = get_logger(self.__class__.__name__)  # Store logger reference

        # Load the UI
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "network_settings.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("NetworkSettings UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load NetworkSettings UI file: {e}")

        # Initialize UI components
        # Navigation buttons
        self.networkSettingsBackButton = self.findChild(QPushButton, "networkSettingsBackButton")
        self.networkInfoBackButton = self.findChild(QPushButton, "networkInfoBackButton")
        self.staticIPSettingsCancelButton = self.findChild(QPushButton, "staticIPSettingsCancelButton")
        self.wifiSettingsCancelButton = self.findChild(QPushButton, "wifiSettingsCancelButton")

        # Action buttons
        self.networkInfoButton = self.findChild(QPushButton, "networkInfoButton")
        self.configureStaticIPButton = self.findChild(QPushButton, "configureStaticIPButton")
        self.configureWifiButton = self.findChild(QPushButton, "configureWifiButton")
        self.staticIPSettingsDoneButton = self.findChild(QPushButton, "staticIPSettingsDoneButton")
        self.wifiSettingsDoneButton = self.findChild(QPushButton, "wifiSettingsDoneButton")
        self.deleteStaticIPSettingsButton = self.findChild(QPushButton, "deleteStaticIPSettingsButton")
        self.clearNetworkSettingsButton = self.findChild(QPushButton, "clearNetworkSettingsButton")

        # Keyboard buttons
        self.staticIPKeyboardButton = self.findChild(QPushButton, "staticIPKeyboardButton")
        self.staticIPGatewayKeyboardButton = self.findChild(QPushButton, "staticIPGatewayKeyboardButton")
        self.staticIPNameServerKeyboardButton = self.findChild(QPushButton, "staticIPNameServerKeyboardButton")
        self.wifiSettingsSSIDKeyboardButton = self.findChild(QPushButton, "wifiSettingsSSIDKeyboardButton")

        # UI containers and pages
        self.stackedWidget = self.findChild(QStackedWidget, "stackedWidget")
        self.networkSettingsPage = self.findChild(QWidget, "networkSettingsPage")
        self.networkInfoPage = self.findChild(QWidget, "networkInfoPage")
        self.staticIPSettingsPage = self.findChild(QWidget, "staticIPSettingsPage")
        self.wifiSettingsPage = self.findChild(QWidget, "wifiSettingsPage")

        self.QRCodeLabel = self.findChild(QLabel, "QRCodeLabel")
        self.hiddenCheckBox = self.findChild(QCheckBox, "hiddenCheckBox")

        # Additional UI components for network info display
        self.hostname = self.findChild(QLabel, "hostname")
        self.wifiAp = self.findChild(QLabel, "wifiAp") 
        self.wifiIp = self.findChild(QLabel, "wifiIp")
        self.lanIp = self.findChild(QLabel, "lanIp")
        self.wifiMac = self.findChild(QLabel, "wifiMac")
        self.lanMac = self.findChild(QLabel, "lanMac")
        
        # WiFi settings components
        self.wifiSettingsComboBox = self.findChild(QComboBox, "wifiSettingsComboBox")
        self.staticIPComboBox = self.findChild(QComboBox, "staticIPComboBox")

        # Validate UI components using simplified check_ui_elements
        # Convert all UI components into a single list for validation
        ui_components = [
            self.networkSettingsBackButton, self.networkInfoBackButton,
            self.staticIPSettingsCancelButton, self.wifiSettingsCancelButton,
            self.networkInfoButton, self.configureStaticIPButton,
            self.configureWifiButton, self.staticIPSettingsDoneButton,
            self.wifiSettingsDoneButton, self.deleteStaticIPSettingsButton,
            self.clearNetworkSettingsButton, self.staticIPKeyboardButton,
            self.staticIPGatewayKeyboardButton, self.staticIPNameServerKeyboardButton, 
            self.wifiSettingsSSIDKeyboardButton, self.stackedWidget, 
            self.networkSettingsPage, self.networkInfoPage, self.staticIPSettingsPage, 
            self.wifiSettingsPage, self.QRCodeLabel, self.hostname, self.wifiAp, 
            self.wifiIp, self.lanIp, self.wifiMac, self.lanMac,
            self.wifiSettingsComboBox, self.staticIPComboBox
        ]

        # Validate all components at once
        check_ui_elements(self, ui_components, "NetworkSettings UI Components")

        # Create ClickableLineEdit components
        # Fonts and styles
        font = QtGui.QFont()
        font.setFamily("Gotham")
        font.setPointSize(15)

        # WiFi Password Line Edit
        self.wifiPasswordLineEdit = ClickableLineEdit(self.wifiSettingsPage)
        self.wifiPasswordLineEdit.setGeometry(QtCore.QRect(300, 170, 400, 60))
        self.wifiPasswordLineEdit.setFont(font)
        self.wifiPasswordLineEdit.setStyleSheet(styles.textedit)
        self.wifiPasswordLineEdit.setObjectName("wifiPasswordLineEdit")

        # Static IP Line Edits
        font.setPointSize(11)
        self.staticIPLineEdit = ClickableLineEdit(self.staticIPSettingsPage)
        self.staticIPLineEdit.setGeometry(QtCore.QRect(200, 135, 450, 40))
        self.staticIPLineEdit.setFont(font)
        self.staticIPLineEdit.setStyleSheet(styles.textedit)
        self.staticIPLineEdit.setObjectName("staticIPLineEdit")

        self.staticIPGatewayLineEdit = ClickableLineEdit(self.staticIPSettingsPage)
        self.staticIPGatewayLineEdit.setGeometry(QtCore.QRect(200, 205, 450, 40))
        self.staticIPGatewayLineEdit.setFont(font)
        self.staticIPGatewayLineEdit.setStyleSheet(styles.textedit)
        self.staticIPGatewayLineEdit.setObjectName("staticIPGatewayLineEdit")

        self.staticIPNameServerLineEdit = ClickableLineEdit(self.staticIPSettingsPage)
        self.staticIPNameServerLineEdit.setGeometry(QtCore.QRect(200, 275, 450, 40))
        self.staticIPNameServerLineEdit.setFont(font)
        self.staticIPNameServerLineEdit.setStyleSheet(styles.textedit)
        self.staticIPNameServerLineEdit.setObjectName("staticIPNameServerLineEdit")

        # Connect buttons to their respective functions
        # Navigation buttons
        self.networkSettingsBackButton.clicked.connect(self.go_back_to_settings_screen)
        self.networkInfoBackButton.clicked.connect(self.go_back)
        self.staticIPSettingsCancelButton.clicked.connect(
            lambda: self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
        )
        self.wifiSettingsCancelButton.clicked.connect(self.cancel_network_settings)

        # Action buttons
        self.networkInfoButton.clicked.connect(self.networkInfo)
        self.configureStaticIPButton.clicked.connect(self.staticIPSettings)
        self.configureWifiButton.clicked.connect(self.wifiSettings)
        self.staticIPSettingsDoneButton.clicked.connect(self.staticIPSaveStaticNetworkInfo)
        self.wifiSettingsDoneButton.clicked.connect(self.acceptWifiSettings)
        self.clearNetworkSettingsButton.clicked.connect(self.clearNetworkSettings)
        self.hiddenCheckBox.stateChanged.connect(self.togglePasswordVisibility)

        # Set the default page in stacked widget
        self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
        self.logger.info("Set default page to networkSettingsPage")

    def showEvent(self, event):
        """Reset to networkSettingsPage whenever this widget is shown."""
        super().showEvent(event)
        try:
            self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
            self.logger.debug("Reset stacked widget to networkSettingsPage on show")
        except Exception as e:
            self.logger.error(f"Error resetting to networkSettingsPage: {e}")

        # Connect text input fields to keyboard
        # Text Input events
        self.wifiPasswordLineEdit.clicked_signal.connect(
            lambda: self.startKeyboard(self.wifiPasswordLineEdit.setText)
        )
        self.staticIPLineEdit.clicked_signal.connect(
            lambda: self.staticIPShowKeyboard(self.staticIPLineEdit)
        )
        self.staticIPGatewayLineEdit.clicked_signal.connect(
            lambda: self.staticIPShowKeyboard(self.staticIPGatewayLineEdit)
        )
        self.staticIPNameServerLineEdit.clicked_signal.connect(
            lambda: self.staticIPShowKeyboard(self.staticIPNameServerLineEdit)
        )
        self.wifiSettingsSSIDKeyboardButton.clicked.connect(
            lambda: self.startKeyboard(self.wifiSettingsComboBox.addItem)
        )

        self.staticIPKeyboardButton.clicked.connect(
            lambda: self.staticIPShowKeyboard(self.staticIPLineEdit)
        )
        self.staticIPGatewayKeyboardButton.clicked.connect(
            lambda: self.staticIPShowKeyboard(self.staticIPGatewayLineEdit)
        )
        self.staticIPNameServerKeyboardButton.pressed.connect(
            lambda: self.staticIPShowKeyboard(self.staticIPNameServerLineEdit)
        )
        self.deleteStaticIPSettingsButton.pressed.connect(self.deleteStaticIPSettings)

    ''' -------------------------- NETWORK INFO DISPLAY ---------------------------------- '''

    def networkInfo(self):
        self.logger.info("NetworkSettings.networkInfo started")
        try:
            ipWifi = getIP(ThreadRestartNetworking.WLAN)
            ipEth = getIP(ThreadRestartNetworking.ETH)

            self.hostname.setText(getHostname())
            self.wifiAp.setText(getWifiAp())
            self.wifiIp.setText("Not connected" if not ipWifi else ipWifi)
            self.mainSettingsWidget.main_window.home_screen.ipStatus.setText("Not connected" if not ipWifi else ipWifi)
            self.lanIp.setText("Not connected" if not ipEth else ipEth)
            self.wifiMac.setText(getMac(ThreadRestartNetworking.WLAN).decode('utf8'))
            self.lanMac.setText(getMac(ThreadRestartNetworking.ETH).decode('utf8'))
            self.stackedWidget.setCurrentWidget(self.networkInfoPage)
            self.displayQRCode()
        except Exception as e:
            self.logger.error("Error in NetworkSettings.networkInfo: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.networkInfo: {}".format(e), overlay=True)

    def displayQRCode(self):
        # Display QR Code
        try:
            if getIP(ThreadRestartNetworking.ETH) is not None:
                qrip = getIP(ThreadRestartNetworking.ETH)
            elif getIP(ThreadRestartNetworking.WLAN) is not None:
                qrip = getIP(ThreadRestartNetworking.WLAN)
            else:
                if dialog.WarningOk(self, "Network Disconnected"):
                    return
            self.QRCodeLabel.setPixmap(
                qrcode.make("http://" + qrip, image_factory=Image).pixmap())
            # self.stackedWidget.setCurrentWidget(self.QRCodePage)
        except Exception as e:
            self.logger.error("Error in Network Settings: QR CODE {}".format(e))
            dialog.WarningOk(self, "Error in Network Settings: QR CODE {}".format(e), overlay=True)

    def startKeyboard(self, returnFn, onlyNumeric=False, noSpace=False, text=""):
        """
        starts the keyboard screen for entering Password
        """
        self.logger.info("NetworkSettings.startKeyboard started")
        try:
            keyBoardobj = keyboard.Keyboard(onlyNumeric=onlyNumeric, noSpace=noSpace, text=text)
            keyBoardobj.keyboard_signal.connect(returnFn)
            keyBoardobj.setWindowFlags(QtCore.Qt.FramelessWindowHint)
            keyBoardobj.show()
        except Exception as e:
            self.logger.error("Error in NetworkSettings.startKeyboard: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.startKeyboard: {}".format(e), overlay=True)

    ''' -------------------------- WIFI SETTINGS ---------------------------------- '''

    def wifiSettings(self):
        self.logger.info("NetworkSettings.wifiSettings started")
        try:
            self.stackedWidget.setCurrentWidget(self.wifiSettingsPage)
            self.wifiSettingsComboBox.clear()
            self.wifiSettingsComboBox.addItems(self.scan_wifi())
            self.wifiPasswordLineEdit.clear()
        except Exception as e:
            self.logger.error("Error in NetworkSettings.wifiSettings: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.wifiSettings: {}".format(e), overlay=True)

    def scan_wifi(self):
        """
        uses linux shell and WIFI interface to scan available networks
        :return: dictionary of the SSID and the signal strength
        """
        self.logger.info("NetworkSettings.scan_wifi started")
        try:
            # scanData = {}
            # print "Scanning available wireless signals available to wlan0"
            scan_result = \
                subprocess.Popen("iwlist wlan0 scan | grep 'ESSID'", stdout=subprocess.PIPE, shell=True).communicate()[0]
            # Processing STDOUT into a dictionary that later will be converted to a json file later
            scan_result = scan_result.decode('utf8').split('ESSID:')  # each ssid and pass from an item in a list ([ssid pass,ssid paas])
            scan_result = [s.strip() for s in scan_result]
            scan_result = [s.strip('"') for s in scan_result]
            scan_result = filter(None, scan_result)
            return scan_result
        except Exception as e:
            self.logger.error("Error in NetworkSettings.scan_wifi: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.scan_wifi: {}".format(e), overlay=True)
            return []

    def acceptWifiSettings(self):
        self.logger.info("NetworkSettings.acceptWifiSettings started")
        try:
            wlan0_config_file = io.open("/etc/wpa_supplicant/wpa_supplicant.conf", "r+", encoding='utf8')
            wlan0_config_file.truncate()
            ascii_ssid = self.wifiSettingsComboBox.currentText()
            # unicode_ssid = ascii_ssid.decode('string_escape').decode('utf-8')
            wlan0_config_file.write(u"country=IN\n")
            wlan0_config_file.write(u"ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\n")
            wlan0_config_file.write(u"update_config=1\n")
            wlan0_config_file.write(u"network={\n")
            wlan0_config_file.write(u'ssid="' + str(ascii_ssid) + '"\n')
            if self.hiddenCheckBox.isChecked():
                wlan0_config_file.write(u'scan_ssid=1\n')
            # wlan0_config_file.write(u"scan_ssid=1\n")
            if str(self.wifiPasswordLineEdit.text()) != "":
                wlan0_config_file.write(u'psk="' + str(self.wifiPasswordLineEdit.text()) + '"\n')
            # wlan0_config_file.write(u"key_mgmt=WPA-PSK\n")
            wlan0_config_file.write(u'}')
            wlan0_config_file.close()
            self.restartWifiThreadObject = ThreadRestartNetworking(ThreadRestartNetworking.WLAN)
            self.restartWifiThreadObject.signal.connect(self.wifiReconnectResult)
            self.restartWifiThreadObject.start()
            self.wifiMessageBox = dialog.dialog(self,
                                                "Restarting networking, please wait...",
                                                icon="exclamation-mark.png",
                                                buttons=QtWidgets.QMessageBox.Cancel)
            if self.wifiMessageBox.exec_() in {QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Cancel}:
                self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
        except Exception as e:
            self.logger.error("Error in NetworkSettings.acceptWifiSettings: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.acceptWifiSettings: {}".format(e), overlay=True)

    def wifiReconnectResult(self, x):
        self.logger.info("NetworkSettings.wifiReconnectResult started")
        try:
            self.wifiMessageBox.setStandardButtons(QtWidgets.QMessageBox.Ok)
            if x is not None:
                print("Ouput from signal " + x)
                self.wifiMessageBox.setLocalIcon('success.png')
                self.wifiMessageBox.setText('Connected, IP: ' + x)
                self.wifiMessageBox.setStandardButtons(QtWidgets.QMessageBox.Ok)
                self.mainSettingsWidget.main_window.home_screen.ipStatus.setText(x)  # sets the IP addr. in the status bar

            else:
                self.wifiMessageBox.setText("Not able to connect to WiFi")
        except Exception as e:
            self.logger.error("Error in NetworkSettings.wifiReconnectResult: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.wifiReconnectResult: {}".format(e), overlay=True)

    def togglePasswordVisibility(self, state):
        """
        Toggles the visibility of the WiFi password based on the hidden checkbox state.
        """
        if state == QtCore.Qt.Checked:
            self.wifiPasswordLineEdit.setEchoMode(QtWidgets.QLineEdit.Password)  # Hide password
        else:
            self.wifiPasswordLineEdit.setEchoMode(QtWidgets.QLineEdit.Normal)  # Show password

    ''' -------------------------- STATIC IP SETTINGS ---------------------------------- '''

    def staticIPSettings(self):
        self.logger.info("NetworkSettings.staticIPSettings started")
        try:
            self.stackedWidget.setCurrentWidget(self.staticIPSettingsPage)
            #add "eth0" and "wlan0" to staticIPComboBox:
            self.staticIPComboBox.clear()
            self.staticIPComboBox.addItems(["eth0", "wlan0"])
        except Exception as e:
            self.logger.error("Error in NetworkSettings.staticIPSettings: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.staticIPSettings: {}".format(e), overlay=True)

    def isIpErr(self, ip):
        return (re.search(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$", ip) is None)

    def showIpErr(self, var):
        return dialog.WarningOk(self, "Invalid input: {0}".format(var))

    def staticIPSaveStaticNetworkInfo(self):
        self.logger.info("NetworkSettings.staticIPSaveStaticNetworkInfo started")
        try:
            txtStaticIPInterface = self.staticIPComboBox.currentText()
            txtStaticIPAddress = str(self.staticIPLineEdit.text())
            txtStaticIPGateway = str(self.staticIPGatewayLineEdit.text())
            txtStaticIPNameServer = str(self.staticIPNameServerLineEdit.text())
            if self.isIpErr(txtStaticIPAddress):
                return self.showIpErr("IP Address")
            if self.isIpErr(txtStaticIPGateway):
                return self.showIpErr("Gateway")
            if txtStaticIPNameServer is not "":
                if self.isIpErr(txtStaticIPNameServer):
                    return self.showIpErr("NameServer")
            Globaltxt = subprocess.Popen("cat /etc/dhcpcd.conf", stdout=subprocess.PIPE, shell=True).communicate()[
                0].decode('utf8')
            staticIPConfig = ""
            # using regex remove all lines staring with "interface" and "static" from txt
            Globaltxt = re.sub(r"interface.*\n", "", Globaltxt)
            Globaltxt = re.sub(r"static.*\n", "", Globaltxt)
            Globaltxt = re.sub(r"^\s+", "", Globaltxt)
            staticIPConfig = "\ninterface {0}\nstatic ip_address={1}/24\nstatic routers={2}\nstatic domain_name_servers=8.8.8.8 8.8.4.4 {3}\n\n".format(
                txtStaticIPInterface, txtStaticIPAddress, txtStaticIPGateway, txtStaticIPNameServer)
            Globaltxt = staticIPConfig + Globaltxt
            with open("/etc/dhcpcd.conf", "w") as f:
                f.write(Globaltxt)

            if txtStaticIPInterface == 'eth0':
                print("Restarting networking for eth0")
                self.restartStaticIPThreadObject = ThreadRestartNetworking(ThreadRestartNetworking.ETH)
                self.restartStaticIPThreadObject.signal.connect(self.staticIPReconnectResult)
                self.restartStaticIPThreadObject.start()
                # self.connect(self.restartStaticIPThreadObject, QtCore.SIGNAL(signal), self.staticIPReconnectResult)
                self.staticIPMessageBox = dialog.dialog(self,
                                                        "Restarting networking, please wait...",
                                                        icon="exclamation-mark.png",
                                                        buttons=QtWidgets.QMessageBox.Cancel)
                if self.staticIPMessageBox.exec_() in {QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Cancel}:
                    self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
            elif txtStaticIPInterface == 'wlan0':
                print("Restarting networking for wlan0")
                self.restartWifiThreadObject = ThreadRestartNetworking(ThreadRestartNetworking.WLAN)
                self.restartWifiThreadObject.signal.connect(self.wifiReconnectResult)
                self.restartWifiThreadObject.start()
                self.wifiMessageBox = dialog.dialog(self,
                                                    "Restarting networking, please wait...",
                                                    icon="exclamation-mark.png",
                                                    buttons=QtWidgets.QMessageBox.Cancel)
                if self.wifiMessageBox.exec_() in {QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Cancel}:
                    self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
        except Exception as e:
            self.logger.error("Error in NetworkSettings.staticIPSaveStaticNetworkInfo: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.staticIPSaveStaticNetworkInfo: {}".format(e), overlay=True)

    def deleteStaticIPSettings(self):
        self.logger.info("NetworkSettings.deleteStaticIPSettings started")
        try:
            Globaltxt = subprocess.Popen("cat /etc/dhcpcd.conf", stdout=subprocess.PIPE, shell=True).communicate()[
                0].decode('utf8')
            # using regex remove all lines staring with "interface" and "static" from txt
            Globaltxt = re.sub(r"interface.*\n", "", Globaltxt)
            Globaltxt = re.sub(r"static.*\n", "", Globaltxt)
            Globaltxt = re.sub(r"^\s+", "", Globaltxt)
            with open("/etc/dhcpcd.conf", "w") as f:
                f.write(Globaltxt)
            self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
        except Exception as e:
            self.logger.error("Error in NetworkSettings.deleteStaticIPSettings: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.deleteStaticIPSettings: {}".format(e), overlay=True)

    def staticIPReconnectResult(self, x):
        self.logger.info("NetworkSettings.staticIPReconnectResult started")
        try:
            self.staticIPMessageBox.setStandardButtons(QtWidgets.QMessageBox.Ok)
            if x is not None:
                self.staticIPMessageBox.setLocalIcon('success.png')
                self.staticIPMessageBox.setText('Connected, IP: ' + x)
            else:

                self.staticIPMessageBox.setText("Not able to set Static IP")
        except Exception as e:
            self.logger.error("Error in NetworkSettings.staticIPReconnectResult: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.staticIPReconnectResult: {}".format(e), overlay=True)

    def staticIPShowKeyboard(self, textbox):
        self.logger.info("NetworkSettings.staticIPShowKeyboard started")
        try:
            self.startKeyboard(textbox.setText, onlyNumeric=True, noSpace=True, text=str(textbox.text()))
        except Exception as e:
            self.logger.error("Error in NetworkSettings.staticIPShowKeyboard: {}".format(e))
            dialog.WarningOk(self, "Error in NetworkSettings.staticIPShowKeyboard: {}".format(e), overlay=True)

    def cancel_network_settings(self):
        """Cancel network settings change and return to main network page."""
        self.logger.info("Cancel Network Settings button clicked")
        self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
        self.logger.info("Returned to network settings page after cancel")

    def clearNetworkSettings(self):
        """Clear all network settings and restore to default configuration."""
        self.logger.info("Clear network settings button clicked")
        
        # Show confirmation dialog
        result = dialog.WarningYesNo(
            self,
            "Are you sure you want to restore all network settings to default?\n\n"
            "This will:\n"
            "• Reset WiFi configuration to factory defaults\n"
            "• Remove all static IP settings\n"
            "• Restore DHCP configuration\n"
            "• Require network reconfiguration after restart\n\n"
            "The system may need to be restarted for changes to take effect.",
            fontSize=12,
            overlay=True
        )
        
        if result:  # User clicked Yes
            try:
                self.logger.info("User confirmed network settings reset")
                
                # Determine config directory path relative to this file
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # Navigate up to octoprint_ControlCenter directory, then to config
                config_dir = os.path.join(current_dir, "..", "..", "..", "config")
                config_dir = os.path.abspath(config_dir)
                
                self.logger.info(f"Using config directory: {config_dir}")
                
                # Restore dhcpcd.conf
                dhcpcd_source = os.path.join(config_dir, "dhcpcd.conf")
                dhcpcd_cmd = ["sudo", "cp", "-f", dhcpcd_source, "/etc/dhcpcd.conf"]
                self.logger.info(f"Executing: {' '.join(dhcpcd_cmd)}")
                dhcpcd_result = subprocess.run(dhcpcd_cmd, capture_output=True, text=True)
                
                # Restore wpa_supplicant.conf
                wpa_source = os.path.join(config_dir, "wpa_supplicant.conf")  
                wpa_cmd = ["sudo", "cp", "-f", wpa_source, "/etc/wpa_supplicant/wpa_supplicant.conf"]
                self.logger.info(f"Executing: {' '.join(wpa_cmd)}")
                wpa_result = subprocess.run(wpa_cmd, capture_output=True, text=True)
                
                if dhcpcd_result.returncode == 0 and wpa_result.returncode == 0:
                    # Success dialog
                    dialog.SuccessOk(
                        self,
                        "Network settings have been successfully restored to default.\n\n"
                        "Please restart the system for changes to take effect.\n"
                        "After restart, you can reconfigure your network settings.",
                        fontSize=12,
                        overlay=True
                    )
                    self.logger.info("Network settings successfully restored to default")
                    
                    # Return to main network settings page
                    self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
                    
                else:
                    # Error dialog with better error information
                    error_msg = "Failed to restore network settings.\n\n"
                    if dhcpcd_result.returncode != 0:
                        error_msg += f"dhcpcd error: {dhcpcd_result.stderr}\n"
                    if wpa_result.returncode != 0:
                        error_msg += f"wpa_supplicant error: {wpa_result.stderr}\n"
                    error_msg += "\nPlease check system permissions and try again."
                    
                    dialog.ErrorOk(
                        self,
                        error_msg,
                        fontSize=12,
                        overlay=True
                    )
                    self.logger.error(f"Failed to restore network settings. dhcpcd return code: {dhcpcd_result.returncode}, wpa return code: {wpa_result.returncode}")
                    if dhcpcd_result.stderr:
                        self.logger.error(f"dhcpcd stderr: {dhcpcd_result.stderr}")
                    if wpa_result.stderr:
                        self.logger.error(f"wpa stderr: {wpa_result.stderr}")
                    
            except Exception as e:
                self.logger.error(f"Exception during network settings reset: {e}")
                dialog.ErrorOk(
                    self,
                    f"An error occurred while restoring network settings:\n\n{str(e)}\n\n"
                    "Please check the system logs for more details.",
                    fontSize=12,
                    overlay=True
                )
        else:
            self.logger.info("User cancelled network settings reset")

    def go_back_to_settings_screen(self):
        """Return to the main settings screen."""
        self.logger.info("Back to settings screen button clicked")
        self.mainSettingsWidget.stackedWidget.setCurrentWidget(self.mainSettingsWidget.mainSettingsPage)
        self.logger.info("Navigated back to main settings screen")

    def go_back(self):
        """Return to main network settings page from network info page."""
        self.logger.info("Back to network settings page button clicked")
        self.stackedWidget.setCurrentWidget(self.networkSettingsPage)
        self.logger.info("Navigated back to network settings page")
