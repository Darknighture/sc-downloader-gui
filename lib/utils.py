import os
import sys

from PyQt5.QtWidgets import QMessageBox


def app_dir():
    """Absolute path of the directory that holds the application.

    Works both when running from source and from a frozen executable, so the
    app no longer depends on the process working directory.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))

    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE_DIR = app_dir()

CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')


def resource_path(*parts):
    """Absolute path to a bundled resource such as ``ui/assets/start.png``."""
    return os.path.join(BASE_DIR, *parts)


def join_path(*path):
    return '/'.join(path)


def is_masterhash_valid(masterhash):
    return len(masterhash) == 40 and all(char in '0123456789abcdef' for char in masterhash)


def is_fingerprint_valid(fingerprint):
    if 'sha' in fingerprint:
        if 'files' in fingerprint:
            for file in fingerprint['files']:
                if 'file' not in file:
                    return False

        else:
            return False

    else:
        return False

    return True


def build_alert_box(title, message):
    msg = QMessageBox()
    msg.setWindowTitle(title)
    msg.setText("""<p style='text-align: center;'><img src='{}' alt='' width='42' height='42'/></p>
                   <p style='align: center;'><strong>{}</strong></p>""".format(
        resource_path('ui', 'assets', 'warning-icon.png').replace('\\', '/'), message))

    msg.exec_()
