import os
import subprocess
from PyQt5 import uic, QtGui, QtCore
from PyQt5.QtWidgets import QWidget, QPushButton, QStackedWidget, QListWidget, QLabel, QToolButton
from utils.helpers import check_ui_elements
from utils.logger import get_logger
from utils import dialog
import base64
from datetime import datetime

from utils.helpers import run_async
from utils.hurry.filesize.filesize import size



class ThreadFileUpload(QtCore.QThread):
    """Thread to handle file uploads to OctoPrint without blocking UI"""
    
    upload_complete_signal = QtCore.pyqtSignal(bool, str)
    
    def __init__(self, file, print_after_upload=False):
        """Initialize the file upload thread"""
        super(ThreadFileUpload, self).__init__()
        self.file = file
        self.print_after_upload = print_after_upload
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info(f"Initialized ThreadFileUpload for {file}")

    def run(self):
        """Run the file upload process"""
        from octoprint_client import octoprint_singleton
        
        self.logger.info(f"Starting file upload: {self.file}")
        try:
            # Check if there's a thumbnail image to upload
            if self.file.lower().endswith('.gcode'):
                thumbnail_file = self.file.replace(".gcode", ".png")
                try:
                    import os
                    if os.path.exists(thumbnail_file):
                        self.logger.info(f"Uploading thumbnail: {thumbnail_file}")
                        octoprint_singleton.get_client().uploadImage(thumbnail_file)
                except Exception as e:
                    self.logger.error(f"Failed to upload thumbnail: {e}")
            
            # Upload the gcode file
            if self.print_after_upload:
                self.logger.info(f"Uploading and printing file: {self.file}")
                octoprint_singleton.get_client().uploadGcode(file=self.file, select=True, prnt=True)
            else:
                self.logger.info(f"Uploading file: {self.file}")
                octoprint_singleton.get_client().uploadGcode(file=self.file, select=False, prnt=False)
                
            self.upload_complete_signal.emit(True, self.file)
            self.logger.info("File upload completed successfully")
            
        except Exception as e:
            self.logger.error(f"File upload failed: {e}")
            self.upload_complete_signal.emit(False, str(e))


class PrintFromLocation(QWidget):
    def __init__(self, main_window):
        """Initialize the PrintFromLocation screen with all UI components and connections."""
        super(PrintFromLocation, self).__init__()
        self.main_window = main_window
        self.octoprint_client = main_window.octoprint_client

        # Use centralized logger
        self.logger = get_logger(self.__class__.__name__)
        self.logger.info("Initializing PrintFromLocation screen")

        # Load the UI file with proper error handling
        try:
            # Use relative path from the current module's directory
            ui_file_path = os.path.join(os.path.dirname(__file__), "print_from_location.ui")
            uic.loadUi(ui_file_path, self)
            self.logger.info("PrintFromLocation UI loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to load PrintFromLocation UI file: {e}")
            return

        # Initialize UI components directly
        self.logger.debug("Initializing UI components")

        # Main container widget
        self.stackedWidget = self.findChild(QStackedWidget, "stackedWidget")

        # Pages for stacked widget
        self.printLocationPage = self.findChild(QWidget, "printLocationPage")
        self.fileListLocalPage = self.findChild(QWidget, "fileListLocalPage")
        self.fileListUSBPage = self.findChild(QWidget, "fileListUSBPage")
        self.printSelectedLocalPage = self.findChild(QWidget, "printSelectedLocalPage")
        self.printSelectedUSBPage = self.findChild(QWidget, "printSelectedUSBPage")

        # USB storage related buttons
        self.USBStorageBackButton = self.findChild(QPushButton, "USBStorageBackButton")
        self.USBStorageScrollDown = self.findChild(QPushButton, "USBStorageScrollDown")
        self.USBStorageScrollUp = self.findChild(QPushButton, "USBStorageScrollUp")
        self.USBStorageSelectButton = self.findChild(QPushButton, "USBStorageSelectButton")
        self.USBStorageSaveButton = self.findChild(QPushButton, "USBStorageSaveButton")

        # Local storage related buttons
        self.localStorageBackButton = self.findChild(QPushButton, "localStorageBackButton")
        self.localStorageScrollDown = self.findChild(QPushButton, "localStorageScrollDown")
        self.localStorageScrollUp = self.findChild(QPushButton, "localStorageScrollUp")
        self.localStorageSelectButton = self.findChild(QPushButton, "localStorageSelectButton")
        self.localStorageDeleteButton = self.findChild(QPushButton, "localStorageDeleteButton")

        # Location selection buttons
        self.fromUsbButton = self.findChild(QPushButton, "fromUsbButton")
        self.fromLocalButton = self.findChild(QPushButton, "fromLocalButton")
        self.printLocationScreenBackButton = self.findChild(QPushButton, "printLocationScreenBackButton")

        # Selected file buttons - USB
        self.fileSelectedUSBPrintButton = self.findChild(QToolButton, "fileSelectedUSBPrintButton")
        self.fileSelectedUSBTransferButton = self.findChild(QToolButton, "fileSelectedUSBTransferButton")
        self.fileSelectedUSBBackButton = self.findChild(QPushButton, "fileSelectedUSBBackButton")

        # Selected file buttons - Local
        self.fileSelectedLocalPrintButton = self.findChild(QToolButton, "fileSelectedLocalPrintButton")
        self.fileSelectedLocalBackButton = self.findChild(QPushButton, "fileSelectedLocalBackButton")

        # List widgets
        self.fileListWidgetLocal = self.findChild(QListWidget, "fileListWidgetLocal")
        self.fileListWidgetUSB = self.findChild(QListWidget, "fileListWidgetUSB")

        # Preview and info labels
        self.fileSelectedLocalName = self.findChild(QLabel, "fileSelectedLocalName")
        self.fileSelectedUSBName = self.findChild(QLabel, "fileSelectedUSBName")
        self.printPreviewSelectedLocal = self.findChild(QLabel, "printPreviewSelectedLocal")
        self.printPreviewSelectedUSB = self.findChild(QLabel, "printPreviewSelectedUSB")

        # Check all UI elements exist in one consolidated list
        check_ui_elements(self, [
            # Main container
            self.stackedWidget,

            # Pages
            self.printLocationPage, self.fileListLocalPage, self.fileListUSBPage,
            self.printSelectedLocalPage, self.printSelectedUSBPage,

            # USB storage buttons
            self.USBStorageBackButton, self.USBStorageScrollDown, self.USBStorageScrollUp,
            self.USBStorageSelectButton, self.USBStorageSaveButton,

            # Local storage buttons
            self.localStorageBackButton, self.localStorageScrollDown, self.localStorageScrollUp,
            self.localStorageSelectButton, self.localStorageDeleteButton,

            # Location selection buttons
            self.fromUsbButton, self.fromLocalButton, self.printLocationScreenBackButton,

            # USB file buttons
            self.fileSelectedUSBPrintButton, self.fileSelectedUSBTransferButton, self.fileSelectedUSBBackButton,

            # Local file buttons
            self.fileSelectedLocalPrintButton, self.fileSelectedLocalBackButton,

            # List widgets
            self.fileListWidgetLocal, self.fileListWidgetUSB,

            # Info labels
            self.fileSelectedLocalName, self.fileSelectedUSBName,
            self.printPreviewSelectedLocal, self.printPreviewSelectedUSB
        ], "PrintFromLocation - All UI Elements")

        # Connect all button signals with safety checks to prevent NoneType errors
        self.logger.debug("Connecting button signals")

        # ! USB storage navigation
        self.USBStorageBackButton.clicked.connect(
            lambda: self.stackedWidget.setCurrentWidget(self.printLocationPage)
        )
        self.USBStorageScrollDown.clicked.connect(
            lambda: self.fileListWidgetUSB.setCurrentRow(self.fileListWidgetUSB.currentRow() + 1)
        )
        self.USBStorageScrollUp.clicked.connect(
            lambda: self.fileListWidgetUSB.setCurrentRow(self.fileListWidgetUSB.currentRow() - 1)
        )
        self.USBStorageSelectButton.clicked.connect(self.printSelectedUSB)
        self.USBStorageSaveButton.clicked.connect(self.transferToLocal)

    # ! Local storage navigation
        self.localStorageBackButton.clicked.connect(
            lambda: self.stackedWidget.setCurrentWidget(self.printLocationPage)
        )
        self.localStorageScrollDown.clicked.connect(
            lambda: self.fileListWidgetLocal.setCurrentRow(self.fileListWidgetLocal.currentRow() + 1)
        )
        self.localStorageScrollUp.clicked.connect(
            lambda: self.fileListWidgetLocal.setCurrentRow(self.fileListWidgetLocal.currentRow() - 1)
        )
        self.localStorageSelectButton.clicked.connect(self.printSelectedLocal)
        self.localStorageDeleteButton.clicked.connect(self.deleteItem)

    # ! Location selection buttons
        self.fromUsbButton.clicked.connect(self.fileListUSB)
        self.fromLocalButton.clicked.connect(self.fileListLocal)
        self.printLocationScreenBackButton.clicked.connect(self.main_window.switch_to_menu_screen)

    # ! Selected file buttons - USB
        self.fileSelectedUSBPrintButton.clicked.connect(lambda: self.transferToLocal(prnt=True))
        self.fileSelectedUSBTransferButton.clicked.connect(lambda: self.transferToLocal(prnt=False))
        self.fileSelectedUSBBackButton.clicked.connect(self.fileListUSB)

    # ! Selected file buttons - Local
        self.fileSelectedLocalPrintButton.clicked.connect(self.printFile)
        self.fileSelectedLocalBackButton.clicked.connect(self.fileListLocal)

    # ! Set the default screen to printLocationPage if it exists
        self.stackedWidget.setCurrentWidget(self.printLocationPage)
        self.logger.info("Set initial page to printLocationPage")


    ''' ------------------------ HELPER METHODS -------------------------- '''

    def fileListLocal(self):
        """
        Gets the file list from octoprint server, displays it on the list, as well as
        sets the stacked widget page to the file list page
        """
        self.logger.info("PrintFromLocation.fileListLocal started")
        try:
            self.stackedWidget.setCurrentWidget(self.fileListLocalPage)
            files = []
            for file in self.octoprint_client.retrieveFileInformation()['files']:
                if file["type"] == "machinecode":
                    files.append(file)

            self.fileListWidgetLocal.clear()
            files.sort(key=lambda d: d['date'], reverse=True)
            # for item in [f['name'] for f in files] :
            #     self.fileListWidget.addItem(item)
            self.fileListWidgetLocal.addItems([f['name'] for f in files])
            self.fileListWidgetLocal.setCurrentRow(0)
        except Exception as e:
            self.logger.error("Error in PrintFromLocation.fileListLocal: {}".format(e))
            dialog.WarningOk(self, "Error in PrintFromLocation.fileListLocal: {}".format(e), overlay=True)

    def fileListUSB(self):
        """
        Gets the file list from octoprint server, displays it on the list, as well as
        sets the stacked widget page to the file list page
        ToDO: Add deapth of folders recursively get all gcodes
        """
        self.logger.info("PrintFromLocation.fileListUSB started")
        try:
            self.stackedWidget.setCurrentWidget(self.fileListUSBPage)
            self.fileListWidgetUSB.clear()
            files = subprocess.Popen("ls /media/usb0 | grep gcode", stdout=subprocess.PIPE, shell=True).communicate()[0]
            files = files.decode('utf-8').split('\n')
            files = filter(None, files)
            # for item in files:
            #     self.fileListWidgetUSB.addItem(item)
            self.fileListWidgetUSB.addItems(files)
            self.fileListWidgetUSB.setCurrentRow(0)
        except Exception as e:
            self.logger.error("Error in PrintFromLocation.fileListUSB: {}".format(e))
            dialog.WarningOk(self, "Error in PrintFromLocation.fileListUSB: {}".format(e), overlay=True)

    def printSelectedLocal(self):

        """
        gets information about the selected file from octoprint server,
        as well as sets the current page to the print selected page.
        This function also selects the file to print from octoprint
        """
        self.logger.info("PrintFromLocation.printSelectedLocal started")
        try:
            current_item = self.fileListWidgetLocal.currentItem()
            if current_item is None:
                return
            self.fileSelectedLocalName.setText(current_item.text())
            self.stackedWidget.setCurrentWidget(self.printSelectedLocalPage)
            file = self.octoprint_client.retrieveFileInformation(
                current_item.text())
            try:
                self.fileSizeSelected.setText(size(file['size']))
            except KeyError:
                self.fileSizeSelected.setText('-')
            try:
                self.fileDateSelected.setText(datetime.fromtimestamp(file['date']).strftime('%d/%m/%Y %H:%M:%S'))
            except KeyError:
                self.fileDateSelected.setText('-')
            try:
                m, s = divmod(file['gcodeAnalysis']['estimatedPrintTime'], 60)
                h, m = divmod(m, 60)
                d, h = divmod(h, 24)
                self.filePrintTimeSelected.setText("%dd:%dh:%02dm:%02ds" % (d, h, m, s))
            except KeyError:
                self.filePrintTimeSelected.setText('-')
            try:
                self.filamentVolumeSelected.setText(
                    ("%.2f cm" % file['gcodeAnalysis']['filament']['tool0']['volume']) + chr(179))
            except KeyError:
                self.filamentVolumeSelected.setText('-')

            try:
                self.filamentLengthFileSelected.setText(
                    "%.2f mm" % file['gcodeAnalysis']['filament']['tool0']['length'])
            except KeyError:
                self.filamentLengthFileSelected.setText('-')
            # uncomment to select the file when selectedd in list
            # octopiclient.selectFile(self.fileListWidget.currentItem().text(), False)
            self.stackedWidget.setCurrentWidget(self.printSelectedLocalPage)

            '''
            If image is available from server, set it, otherwise display default image
            '''
            self.displayThumbnail(self.printPreviewSelectedLocal, str(current_item.text()),
                                  usb=False)

        except Exception as e:
            self.logger.error("Error in PrintFromLocation.printSelectedLocal: {}".format(e))
            dialog.WarningOk(self, "Error in PrintFromLocation.printSelectedLocal: {}".format(e), overlay=True)

    def printSelectedUSB(self):
        """
        Sets the screen to the print selected screen for USB, on which you can transfer to local drive and view preview image.
        :return:
        """
        self.logger.info("PrintFromLocation.printSelectedUSB started")
        try:
            current_item = self.fileListWidgetUSB.currentItem()
            if current_item is None:
                self.logger.warning("No file selected in USB list")
                dialog.WarningOk(self, "Please select a file first", overlay=True)
                return
            
            self.fileSelectedUSBName.setText(current_item.text())
            self.stackedWidget.setCurrentWidget(self.printSelectedUSBPage)
            self.displayThumbnail(self.printPreviewSelectedUSB,
                                  '/media/usb0/' + str(current_item.text()), usb=True)
        except Exception as e:
            self.logger.error("Error in PrintFromLocation.printSelectedUSB: {}".format(e))
            dialog.WarningOk(self, "Error in PrintFromLocation.printSelectedUSB: {}".format(e), overlay=True)

    def deleteItem(self):
        """
        Deletes a gcode file, and if associates, its image file from the memory
        """
        self.logger.info("PrintFromLocation.deleteItem started")
        try:
            current_item = self.fileListWidgetLocal.currentItem()
            if current_item is None:
                return
            filename = current_item.text()
            self.logger.info(f"Attempting to delete file: {filename}")
            
            # Delete the main gcode file
            try:
                self.octoprint_client.deleteFile(filename)
                self.logger.info(f"Successfully deleted main file: {filename}")
            except Exception as e:
                if "404" in str(e):
                    self.logger.warning(f"File {filename} not found, may have been already deleted")
                else:
                    raise e
            
            # Delete associated PNG file if it exists
            png_filename = filename.replace(".gcode", ".png")
            try:
                self.octoprint_client.deleteFile(png_filename)
                self.logger.info(f"Successfully deleted PNG file: {png_filename}")
            except Exception as e:
                if "404" in str(e):
                    self.logger.warning(f"PNG file {png_filename} not found, skipping")
                else:
                    self.logger.warning(f"Failed to delete PNG file {png_filename}: {e}")
            
            # Refresh the file list
            self.fileListLocal()
            
        except Exception as e:
            self.logger.error("Error in PrintFromLocation.deleteItem: {}".format(e))
            dialog.WarningOk(self, "Error in PrintFromLocation.deleteItem: {}".format(e), overlay=True)

    def transferToLocal(self, prnt=False):
        """
        Transfers a file from USB mounted at /media/usb0 to octoprint's watched folder so that it gets automatically detected bu Octoprint.
        Warning: If the file is read-only, octoprint API for reading the file crashes.
        """
        self.logger.info("PrintFromLocation.transferToLocal started")
        try:
            current_item = self.fileListWidgetUSB.currentItem()
            if current_item is None:
                return
            file = '/media/usb0/' + str(current_item.text())

            self.uploadThread = ThreadFileUpload(file, print_after_upload=prnt)
            self.uploadThread.start()
            if prnt:
                self.main_window.switch_to_home_screen()
        except Exception as e:
            self.logger.error("Error in PrintFromLocation.transferToLocal: {}".format(e))
            dialog.WarningOk(self, "Error in PrintFromLocation.transferToLocal: {}".format(e), overlay=True)

    def printFile(self):
        """
        Prints the file selected from printSelected()
        """
        self.logger.info("PrintFromLocation.printFile started")
        try:
            current_item = self.fileListWidgetLocal.currentItem()
            if current_item is None:
                return
            self.octoprint_client.home(['x', 'y', 'z'])
            self.octoprint_client.selectFile(current_item.text(), True)
            self.main_window.controller.checkKlipperPrinterCFG()
            self.main_window.switch_to_home_screen()
        except Exception as e:
            self.logger.error("Error in PrintFromLocation.printFile: {}".format(e))
            dialog.WarningOk(self, "Error in PrintFromLocation.printFile: {}".format(e), overlay=True)

    def getImageFromGcode(self,gcodeLocation):
        """
        Gets the image from the gcode text file when getting it from USB drive
        """
        self.logger.info("PrintFromLocation.getImageFromGcode started")
        try:
            with open(gcodeLocation, 'rb') as f:
                content = f.readlines()[:500]
                content = b''.join(content)
            start = content.find(b'; thumbnail begin')
            end = content.find(b'; thumbnail end')
            if start != -1 and end != -1:
                thumbnail = content[start:end]
                thumbnail = base64.b64decode(thumbnail[thumbnail.find(b'\n') + 1:].replace(b'; ', b'').replace(b'\r\n', b''))
                return thumbnail
            else:
                return False
        except Exception as e:
            self.logger.error("Error in PrintFromLocation.getImageFromGcode: {}".format(e))
            dialog.WarningOk(self, "Error in PrintFromLocation.getImageFromGcode: {}".format(e), overlay=True)
            return False

    @run_async
    def displayThumbnail(self, labelObject, fileLocation, usb=False):
        """
        Displays the image on the label object
        :param labelObject: QLabel object to display the image
        :param fileLocation: location of the file
        :param usb: if the file is from
        """
        self.logger.info("PrintFromLocation.displayThumbnail started")
        try:
            pixmap = QtGui.QPixmap()
            if usb:
                img = self.getImageFromGcode(fileLocation)
            else:
                img = self.octoprint_client.getImage(fileLocation)
            if img:
                pixmap.loadFromData(img)
                labelObject.setPixmap(pixmap)
            else:
                # Use resource path for thumbnail image
                labelObject.setPixmap(QtGui.QPixmap(":/Logos & Branding/img/Logos/thumbnail.png"))
        except Exception as e:
            # Use resource path for thumbnail image
            labelObject.setPixmap(QtGui.QPixmap(":/Logos & Branding/img/Logos/thumbnail.png"))
            self.logger.error("Error in PrintFromLocation.displayThumbnail: {}".format(e))

    def showEvent(self, a0):
        """Reset to printLocationPage whenever this widget is shown from main window navigation."""
        super().showEvent(a0)
        try:
            self.stackedWidget.setCurrentWidget(self.printLocationPage)
            self.logger.debug("Reset stacked widget to printLocationPage on show")
        except Exception as e:
            self.logger.error(f"Error resetting to printLocationPage: {e}")
