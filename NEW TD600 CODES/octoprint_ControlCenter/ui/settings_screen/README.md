# Settings Screen

This directory contains the settings screen widgets for the application. Each settings screen widget is dynamically loaded and integrated into the main settings screen.

## Structure

Each settings screen widget should be placed in its own subfolder within the `settings_screen` directory. The subfolder should contain the following files:

- `<widget_name>.ui`: The UI file for the widget, created using Qt Designer.
- `<widget_name>.py`: The backend Python file for the widget.

The naming convention for the files should follow the pattern `<widget_name>.ui` and `<widget_name>.py`, where `<widget_name>` is the name of the widget.

## Example

For a widget named `example_widget`, the structure should be as follows:

settings_screen/ example_widget/ example_widget.ui example_widget.py

### example_widget.ui

The `.ui` file should define the layout and components of the widget using Qt Designer.

### example_widget.py

The `.py` file should define the backend logic for the widget. The class name in the `.py` file should match the widget name in title case with underscores removed. For example, the class name for `example_widget.py` should be `ExampleWidget`.

```python
from PyQt5 import uic
from PyQt5.QtWidgets import QWidget

class ExampleWidget(QWidget):
    def __init__(self, parent, settings_screen):
        super(ExampleWidget, self).__init__(parent)
        self.mainSettingsWidget = settings_screen  # Reference to the main settings widget
        uic.loadUi('octoprint_ControlCenter/ui/settings_screen/example_widget/example_widget.ui', self)

        # Example of connecting a button to a function
        self.exampleButton = self.findChild(QPushButton, 'exampleButton')
        self.exampleButton.clicked.connect(self.example_function)

    def example_function(self):
        # Placeholder for example function logic
        print("Example button clicked")

    def go_back(self):
        # Logic to go back to the settings screen
        print("Back button clicked")
        self.mainSettingsWidget.stackedWidget.setCurrentWidget(self.mainSettingsWidget.mainSettingsPage)
```



### Adding a New Settings Widget
To add a new settings widget, follow these steps:

1. Create a new subfolder in the settings_screen directory with the name of the widget.
2. Create the .ui file using Qt Designer and save it in the subfolder.
3. Create the .py file with the backend logic and save it in the subfolder.
4. Ensure the class name in the .py file matches the widget name in title case with underscores removed.
5. The new widget will be dynamically loaded and integrated into the main settings screen.


By following this structure, you can easily add new settings widgets to the application and ensure they are dynamically loaded and integrated into the main settings screen.