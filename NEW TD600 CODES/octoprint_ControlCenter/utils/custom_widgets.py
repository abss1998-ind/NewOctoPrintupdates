from PyQt5 import QtWidgets, QtCore

class ClickableLineEdit(QtWidgets.QLineEdit):
    clicked_signal = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def mousePressEvent(self, QMouseEvent):
        # Emit the clicked signal when the line edit is clicked
        self.clicked_signal.emit()
        # Call the base class implementation to ensure default behavior
        super().mousePressEvent(QMouseEvent)