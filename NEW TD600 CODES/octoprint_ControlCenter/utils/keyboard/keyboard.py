import os
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from functools import partial
import ui.resources.resource_rc





class Keyboard(QtWidgets.QDialog):
    '''
    Class that sets up the win_keyboard UI and functionality
    '''

    keyboard_signal = QtCore.pyqtSignal('PyQt_PyObject')

    def __init__(self, parent=None, onlyNumeric=False, noSpace=False, text=""):
        super(Keyboard, self).__init__(parent)

        # Load the UI directly from the .ui file
        # Use relative path from the current module's directory
        ui_file_path = os.path.join(os.path.dirname(__file__), "win_keyboard.ui")
        uic.loadUi(ui_file_path, self)

        self.setAlphaUpperState(False)

        self.setActions()

        self.tbDisplay.setText(text)
        self.setTextFocus()

        self.btBackNumeric.setEnabled(not onlyNumeric)
        self.btSpecialNumeric.setEnabled(not onlyNumeric)

        self.btSpaceAlpha.setEnabled(not noSpace)
        self.btSpaceAlphaU.setEnabled(not noSpace)
        self.btSpaceNumeric.setEnabled(not noSpace)
        self.btSpaceSpecial.setEnabled(not noSpace)

        if not onlyNumeric:
            self.ShowAlpha()
        else:
            self.ShowNumeric()

    def setAlphaUpperState(self, pinned):
        self.mAlphaPinned = pinned
        self.btCaseAlphaU.setChecked(pinned)
        self.btCaseAlphaU.setFlat(pinned)

    def appendTextAndFocus(self, text):
        try:
            self.addText(text)
            if self.pageHolder.currentWidget() == self.pgAlphaU:
                if not self.mAlphaPinned:
                    self.ShowAlpha()
            self.tbDisplay.setFocus()
        except Exception as e:
            print("error Pressing Button: " + str(e))

    def setTextFocus(self):
        self.tbDisplay.moveCursor(QtGui.QTextCursor.End, QtGui.QTextCursor.MoveAnchor)
        self.tbDisplay.setFocus()

    def addText(self, txt):
        cursor = self.tbDisplay.textCursor()
        cursor.insertText(txt)
        self.tbDisplay.setFocus()

    def connectClick(self, s):
        temp = "bt" + s
        button = getattr(self, temp)
        button.clicked.connect(partial(self.appendTextAndFocus, button.text()))

    def HandleAlphaState(self):
        if not self.mAlphaPinned:
            self.setAlphaUpperState(True)
            self.setTextFocus()
        else:
            self.ShowAlpha()

    def ShowAlpha(self):
        self.setAlphaUpperState(False)
        self.pageHolder.setCurrentWidget(self.pgAlpha)
        self.setTextFocus()

    def ShowAlphaU(self):
        self.pageHolder.setCurrentWidget(self.pgAlphaU)
        self.setTextFocus()

    def ShowHome(self):
        self.pageHolder.setCurrentWidget(self.pgAlpha)
        self.setTextFocus()

    def ShowNumeric(self):
        self.pageHolder.setCurrentWidget(self.pgNumeric)
        self.setTextFocus()

    def ShowSpecial(self):
        self.pageHolder.setCurrentWidget(self.pgSpecial)
        self.setTextFocus()

    def Space(self):
        self.addText(" ")
        self.tbDisplay.setFocus()

    def Backspace(self):
        cursor = self.tbDisplay.textCursor()
        pos = cursor.position() - 1
        st = self.tbDisplay.toPlainText()
        # self.ui.tbDisplay.setText(st[:-1])
        if pos >= 0:
            st = st[:pos] + st[(pos + 1):]
            self.tbDisplay.setText(st)
            cursor.setPosition(pos)
            self.tbDisplay.setTextCursor(cursor)
        self.tbDisplay.setFocus()

    # caret
    def CaretLeft(self):
        self.tbDisplay.moveCursor(QtGui.QTextCursor.Left, QtGui.QTextCursor.MoveAnchor)
        self.tbDisplay.setFocus()

    def CaretRight(self):
        self.tbDisplay.moveCursor(QtGui.QTextCursor.Right, QtGui.QTextCursor.MoveAnchor)
        self.tbDisplay.setFocus()

    def CaretStart(self):
        self.tbDisplay.moveCursor(QtGui.QTextCursor.Start, QtGui.QTextCursor.MoveAnchor)
        self.tbDisplay.setFocus()

    def CaretEnd(self):
        self.setTextFocus()

    def setActions(self):
        # Screens
        # Char cases
        self.btCaseAlphaU.clicked.connect(self.HandleAlphaState)
        self.btCaseAlpha.clicked.connect(self.ShowAlphaU)
        # Show Numeric
        self.btNumericAlpha.clicked.connect(self.ShowNumeric)
        self.btNumericAlphaU.clicked.connect(self.ShowNumeric)
        self.btNumericSpecial.clicked.connect(self.ShowNumeric)
        # ShowSpecial
        self.btSpecialAlpha.clicked.connect(self.ShowSpecial)
        self.btSpecialAlphaU.clicked.connect(self.ShowSpecial)
        self.btSpecialNumeric.clicked.connect(self.ShowSpecial)

        # Cursor
        self.btCursorLeft.clicked.connect(self.CaretLeft)
        self.btCursorRight.clicked.connect(self.CaretRight)

        # ASCII
        for i in range(1, 95):
            self.connectClick(str(i))
        # repeated elements
        rep = ["27_2", "56_2", "69_2", "74_2", "79_2", "27_3", "56_3"]
        for i in rep:
            self.connectClick(i)

        # Space
        self.btSpaceAlpha.clicked.connect(self.Space)
        self.btSpaceAlphaU.clicked.connect(self.Space)
        self.btSpaceNumeric.clicked.connect(self.Space)
        self.btSpaceSpecial.clicked.connect(self.Space)

        # Backspace
        self.btBackspaceAlpha.clicked.connect(self.Backspace)
        self.btBackspaceAlphaU.clicked.connect(self.Backspace)
        self.btBackspaceNumeric.clicked.connect(self.Backspace)
        self.btBackspaceSpecial.clicked.connect(self.Backspace)

        # Submit
        self.btSubmitAlpha.clicked.connect(self.submit)
        self.btSubmitAlphaU.clicked.connect(self.submit)
        self.btSubmitNumeric.clicked.connect(self.submit)
        self.btSubmitSpecial.clicked.connect(self.submit)

        # Back
        self.btBackNumeric.clicked.connect(self.ShowHome)
        self.btBackSpecial.clicked.connect(self.ShowHome)

    # Submit
    def submit(self):
        self.close()
        self.keyboard_signal.emit(self.tbDisplay.toPlainText())
        self.tbDisplay.setText("")
