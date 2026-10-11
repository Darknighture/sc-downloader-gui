import os
import sys
import json

import qdarkstyle

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from lib.utils import CONFIG_PATH, resource_path
from ui.main_window import MainWindow


def show_config_missing():
    msg = QMessageBox()
    msg.setWindowTitle('Config missing')
    msg.setText("""<p style='text-align: center;'><img src='{}' alt='' width='42' height='42'/></p>
                           <p style='align: center;'><strong>config.json file is missing, cannot continue !</strong></p>""".format(
        resource_path('ui', 'assets', 'warning-icon.png').replace('\\', '/')))

    msg.exec_()


def main():
    app = QApplication([])

    # QDarkStyle has to be applied after the QApplication exists, otherwise
    # the palette patching is silently skipped.
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

    if not os.path.isfile(CONFIG_PATH):
        show_config_missing()
        return 1

    with open(CONFIG_PATH, encoding='utf-8') as f:
        config = json.load(f)

    application = MainWindow(app, config)

    # Disable window resize and the maximize button
    application.setWindowFlags(Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)
    application.show()
    application.setFixedSize(application.size())

    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
