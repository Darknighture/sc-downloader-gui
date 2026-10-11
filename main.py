import importlib
import json
import os
import sys


# Third-party module -> PyPI distribution name. sc-compression is deliberately
# absent: lib/compression.py implements every format it used to be needed for
# and only falls back to it as an optional LZHAM decoder.
REQUIRED_MODULES = {
    'PyQt5': 'PyQt5',
    'qdarkstyle': 'qdarkstyle',
    'zstandard': 'zstandard',
}


def find_missing_modules():
    """Import every third-party dependency so a missing one can be reported
    as an actionable message instead of a raw ImportError traceback."""
    missing = []
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    return missing


def report_missing_modules(missing):
    packages = sorted({REQUIRED_MODULES[name] for name in missing})
    message = (
        'Missing dependencies: {}\n'
        '\n'
        'Install them from the project directory with:\n'
        '    "{}" -m pip install -r requirements.txt\n'
        '\n'
        'That command must use the same interpreter that runs main.py:\n'
        '    {}'
    ).format(', '.join(packages), sys.executable, sys.executable)

    print(message, file=sys.stderr)

    # A dialog is nicer, but it needs Qt - which may be one of the missing
    # packages. In that case the printed message above is all we can offer.
    if 'PyQt5' not in missing:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        # Held in a local so it stays alive for as long as the dialog is up.
        application = QApplication.instance() or QApplication([])
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle('Missing dependencies')
        box.setText('Missing Python packages: {}'.format(', '.join(packages)))
        box.setInformativeText(
            'Open the project folder and run:\n\n'
            '"{}" -m pip install -r requirements.txt'.format(sys.executable))
        box.exec_()

    return 1


# The dependency check has to run before the application modules are imported:
# they pull in zstandard and PyQt5 at import time.
_MISSING_MODULES = find_missing_modules()
if _MISSING_MODULES:  # pragma: no cover - depends on the environment
    sys.exit(report_missing_modules(_MISSING_MODULES))

import qdarkstyle  # noqa: E402
from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from lib.utils import CONFIG_PATH, resource_path  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


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
