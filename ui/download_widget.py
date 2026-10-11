import os
import json
import time
import zlib
import socket
from struct import unpack

from queue import Queue
from urllib.request import urlopen
from urllib.error import HTTPError

from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit,
                             QCheckBox, QComboBox, QHBoxLayout,
                             QVBoxLayout, QPushButton, QProgressBar,
                             QMessageBox, QFileDialog)

from lib.reader import Reader
from lib.writer import Writer
from lib.worker_launcher import WorkerLauncher
from lib.utils import (join_path, build_alert_box, resource_path,
                       is_fingerprint_valid, is_masterhash_valid)
from ui.download_choice_window import DownloadChoiceWindow

SERVER_PORT = 9339


def receive_exactly(sock, length):
    """Read exactly ``length`` bytes from ``sock``.

    Stops early when the peer closes the connection: a bare ``while length:``
    loop would spin forever on an empty read.
    """
    chunks = []
    remaining = length

    while remaining > 0:
        chunk = sock.recv(remaining)

        if not chunk:
            break

        chunks.append(chunk)
        remaining -= len(chunk)

    return b''.join(chunks)


class DownloadWidget(QWidget):
    def __init__(self, main_window, config):
        super().__init__()

        self.main_window = main_window
        self.config = config
        self.assets_host = None
        self.fingerprint = None

        # Server selection
        self.servers = self.config.get('servers', {"Clash Royale": "game.clashroyaleapp.com"})
        self.selected_server_name = list(self.servers.keys())[0]
        self.selected_server_address = list(self.servers.values())[0]

        # Known CDN hosts per game server (used for fingerprint-file mode)
        self.server_cdn_map = {
            "game.clashroyaleapp.com": "http://game-assets.clashroyaleapp.com",
            "game.brawlstarsgame.com": "https://game-assets.brawlstarsgame.com",
            "game.brawlstars.cn": "https://game-assets.tencent-cloud.com",
            "game.production.clashroyale.cn": "https://cr-cdn.supercellgame.cn",
        }

        # Hosts that use Clash Royale VInt protocol (vs Brawl Stars UInt32)
        self.cr_protocol_hosts = {"game.clashroyaleapp.com", "game.production.clashroyale.cn"}

        # Servers whose handshake is frozen (code 16, no fingerprint).
        # "Latest Patch" can't work for these; Masterhash & Fingerprint file still do.
        self.frozen_handshake_servers = {"game.clashroyaleapp.com", "game.production.clashroyale.cn"}

        # Server -> (major, build, minor) initial version for first Hello.
        # Brawl Stars CN rejects version 0 and needs a specific client version.
        # Values map to wire order [major, build, minor] written by request_login_failed.
        self.server_version_overrides = {
            "game.brawlstars.cn": (69, 0, 100),
        }

        self.major = self.config.get('major', 0)
        self.build = self.config.get('build', 0)
        self.minor = self.config.get('minor', 0)

        # Download bookkeeping
        self.total_files = 0
        self.downloaded_files = 0
        self.failed_files = 0
        self.workers_count = 0
        self.download_start_time = None
        self.download_cancelled = False

        # Snapshots of the settings, read on the GUI thread when a download
        # starts. The launcher must not touch widgets from its own thread.
        self.output_dir = None
        self.decompress_assets = False

        self.download_queue = Queue()
        self.worker_launcher = None
        # Launchers that are still winding down after a Stop. Keeping a
        # reference prevents PyQt from destroying a running QThread, which
        # would abort the whole process.
        self.retired_launchers = []

        self.init_ui()
        self._refresh_download_methods()

    def init_ui(self):
        self.main_layout = QHBoxLayout()

        self.init_left_panel()
        self.init_right_panel()

        self.setLayout(self.main_layout)

    def init_left_panel(self):
        self.left_panel_widget = QWidget()
        self.left_panel_layout = QVBoxLayout()

        # Server selector
        self.server_combo_box = QComboBox()
        self.server_combo_box.addItems(list(self.servers.keys()))
        self.server_combo_box.currentIndexChanged.connect(self.on_server_change)

        self.download_method_combo_box = QComboBox()
        self.download_method_combo_box.addItems(['Latest Patch', 'Masterhash', 'Fingerprint file'])
        self.download_method_combo_box.currentIndexChanged.connect(self.on_combo_box_change)

        self.masterhash_input = QLineEdit()

        self.masterhash_input.setPlaceholderText('Enter a masterhash')
        self.masterhash_input.setAlignment(Qt.AlignCenter)
        self.masterhash_input.setMaxLength(40)
        self.masterhash_input.textChanged.connect(self.on_masterhash_changed)
        self.masterhash_input.hide()

        self.masterhash_validity_widget = QWidget()
        self.masterhash_validity_layout = QHBoxLayout()

        self.masterhash_validity_icon = QLabel()
        self.masterhash_validity_icon.setPixmap(
            QPixmap(resource_path('ui', 'assets', 'warning-icon.png')).scaled(17, 17))
        self.masterhash_validity_label = QLabel('Invalid  hash !')

        self.masterhash_validity_layout.addWidget(self.masterhash_validity_icon)
        self.masterhash_validity_layout.addWidget(self.masterhash_validity_label)

        self.masterhash_validity_widget.setLayout(self.masterhash_validity_layout)
        self.masterhash_validity_widget.hide()

        self.browse_fingerprint_widget = QWidget()
        self.browse_fingerprint_layout = QHBoxLayout()

        self.fingerprint_path_input = QLineEdit()
        self.fingerprint_path_input.setEnabled(False)

        self.browse_fingerprint_button = QPushButton('', self)
        self.browse_fingerprint_button.setIcon(QIcon(resource_path('ui', 'assets', 'browse.png')))
        self.browse_fingerprint_button.setIconSize(QSize(17, 17))
        self.browse_fingerprint_button.clicked.connect(self.browse_fingerprint)

        self.browse_fingerprint_layout.addWidget(self.fingerprint_path_input)
        self.browse_fingerprint_layout.addWidget(self.browse_fingerprint_button)

        self.browse_fingerprint_widget.setLayout(self.browse_fingerprint_layout)
        self.browse_fingerprint_widget.hide()

        self.enable_compression_checkbox = QCheckBox('Decompress compressed\nassets (.sc, .csv and .toml)')

        self.left_panel_layout.addWidget(QLabel('Game:'))
        self.left_panel_layout.addWidget(self.server_combo_box)
        self.left_panel_layout.addWidget(QLabel('Download from:'))
        self.left_panel_layout.addWidget(self.download_method_combo_box)
        self.left_panel_layout.addWidget(self.masterhash_input)
        self.left_panel_layout.addWidget(self.masterhash_validity_widget)
        self.left_panel_layout.addWidget(self.browse_fingerprint_widget)
        self.left_panel_layout.addWidget(self.enable_compression_checkbox)

        self.left_panel_layout.addStretch(1)

        self.left_panel_widget.setLayout(self.left_panel_layout)

        self.main_layout.addWidget(self.left_panel_widget)

    def init_right_panel(self):
        self.right_panel_widget = QWidget()
        self.right_panel_layout = QVBoxLayout()

        self.download_buttons_widget = QWidget()
        self.download_buttons_layout = QHBoxLayout()

        self.start_button = QPushButton('Start Download', self)
        self.start_button.setIcon(QIcon(resource_path('ui', 'assets', 'start.png')))
        self.start_button.setIconSize(QSize(17, 17))
        self.start_button.clicked.connect(self.request_info)

        self.stop_button = QPushButton('Stop', self)
        self.stop_button.setIcon(QIcon(resource_path('ui', 'assets', 'stop.png')))
        self.stop_button.setIconSize(QSize(17, 17))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_download)

        self.download_buttons_layout.addWidget(self.start_button)
        self.download_buttons_layout.addWidget(self.stop_button)

        self.download_buttons_widget.setLayout(self.download_buttons_layout)

        self.progress_bar = QProgressBar(self)

        self.right_panel_layout.addWidget(self.download_buttons_widget)
        self.right_panel_layout.addWidget(self.progress_bar)

        self.right_panel_layout.addStretch(20)

        self.right_panel_widget.setLayout(self.right_panel_layout)

        self.main_layout.addWidget(self.right_panel_widget)

    def on_server_change(self, _):
        server_name = self.server_combo_box.currentText()
        self.selected_server_name = server_name
        self.selected_server_address = self.servers[server_name]
        self._refresh_download_methods()

    def _refresh_download_methods(self):
        if self.selected_server_address in self.frozen_handshake_servers:
            methods = ['Masterhash', 'Fingerprint file']
        else:
            methods = ['Latest Patch', 'Masterhash', 'Fingerprint file']

        self.download_method_combo_box.blockSignals(True)
        self.download_method_combo_box.clear()
        self.download_method_combo_box.addItems(methods)
        self.download_method_combo_box.blockSignals(False)

        self.on_combo_box_change(None)

    def on_combo_box_change(self, _):
        method = self.download_method_combo_box.currentText()

        if method != 'Masterhash':
            self.start_button.setEnabled(True)
            self.masterhash_validity_widget.hide()

        if method == 'Latest Patch':
            self.masterhash_input.hide()
            self.browse_fingerprint_widget.hide()

        elif method == 'Masterhash':
            self.on_masterhash_changed(self.masterhash_input.text())

            self.masterhash_input.show()
            self.browse_fingerprint_widget.hide()

        else:
            self.masterhash_input.hide()
            self.browse_fingerprint_widget.show()

    def browse_fingerprint(self):
        fingerprint_path, _ = QFileDialog.getOpenFileName(self, 'Open fingerprint',
                                                          '', "JSON file (*.json)")

        if fingerprint_path:
            self.fingerprint_path_input.setText(fingerprint_path)

    def request_info(self):
        download_method = self.download_method_combo_box.currentText()

        if download_method == 'Masterhash':
            masterhash = self.masterhash_input.text()

            if not masterhash:
                return build_alert_box('Missing masterhash', 'Please enter a masterhash first !')

            # Skip the (frozen) handshake: fetch the fingerprint directly from
            # the known CDN host using the user-supplied masterhash.
            self.assets_host = self.server_cdn_map.get(
                self.selected_server_address,
                'http://game-assets.clashroyaleapp.com'
            )

            self.main_window.show_loading()
            self.main_window.status_bar_label.setText(
                'Fetching fingerprint for masterhash {}'.format(masterhash))

            self.masterhash_fetcher_thread = MasterhashFetcherThread(self, masterhash)
            self.masterhash_fetcher_thread.fingerprint_fetched.connect(self.on_masterhash_fetched)
            self.masterhash_fetcher_thread.start()
            return

        elif download_method == 'Fingerprint file':
            fingerprint_path = self.fingerprint_path_input.text()

            if fingerprint_path:
                if os.path.isfile(fingerprint_path):
                    with open(fingerprint_path, encoding='utf-8') as f:
                        try:
                            fingerprint = json.load(f)

                            if is_fingerprint_valid(fingerprint):
                                self.fingerprint = fingerprint

                                # Use base URL without masterhash (worker will add it)
                                self.assets_host = self.server_cdn_map.get(
                                    self.selected_server_address,
                                    'http://game-assets.clashroyaleapp.com'
                                )

                                self.main_window.status_bar_label.setText(
                                    'Fingerprint loaded successfully, version: {}'.format(
                                        self.fingerprint.get('version', 'unknown')))

                                # Skip server connection and go directly to download choice
                                files_extension = []
                                for file in self.fingerprint['files']:
                                    ext = os.path.splitext(file['file'])[1]
                                    if ext not in files_extension:
                                        files_extension.append(ext)

                                self.start_button.setEnabled(False)
                                self.download_method_combo_box.setEnabled(False)
                                self.server_combo_box.setEnabled(False)

                                download_choice_windows = DownloadChoiceWindow(self, files_extension)
                                download_choice_windows.show()
                                return

                            else:
                                return build_alert_box('Invalid fingerprint', 'The given fingerprint is missing needed fields !')

                        except json.decoder.JSONDecodeError:
                            return build_alert_box('Invalid fingerprint', 'Couldn\'t parse the given fingerprint !')

                else:
                    return build_alert_box('Fingerprint error', 'Cannot retrieve fingerprint !')

            else:
                return build_alert_box('Missing fingerprint', 'Please select a fingerprint first !')

        self.main_window.show_loading()
        self.main_window.status_bar_label.setText('Fetching assets host & fingerprint from supercell servers')

        self.info_fetcher_thread = InfoFetcherThread(self)
        self.info_fetcher_thread.info_fetched.connect(self.on_info_fetched)

        self.info_fetcher_thread.start()

    def on_info_fetched(self, login_failed):
        self.info_fetcher_thread.quit()

        if login_failed is None:
            self.main_window.reset_status_bar()
            return build_alert_box('Connection error', 'Could not connect to {}:{} (timeout or refused).'.format(
                self.selected_server_address, SERVER_PORT))

        is_cr = self.selected_server_address in self.cr_protocol_hosts

        try:
            # Read status code: Clash Royale uses VInt, Brawl Stars uses UInt32
            login_failed_error_code = login_failed.read_vint() if is_cr else login_failed.read_uint32()
        except Exception as e:
            self.main_window.reset_status_bar()
            return build_alert_box('Download error', 'Could not read the server response: {}'.format(e))

        if login_failed_error_code == 7:
            try:
                fingerprint = self.parse_fingerprint(login_failed, is_cr)
            except Exception as e:
                self.main_window.reset_status_bar()
                return build_alert_box('Download error', 'Could not parse the server response: {}'.format(e))

            if fingerprint is None:
                self.main_window.reset_status_bar()
                return build_alert_box('Download error', 'Couldn\'t find any host to download assets !')

            try:
                self.fingerprint = json.loads(fingerprint)
            except ValueError:
                self.main_window.reset_status_bar()
                return build_alert_box('Download error', 'The server returned an unreadable fingerprint !')

            self._on_fingerprint_ready()
            return

        if login_failed_error_code in (8, 16):
            if not is_cr:
                # BS doesn't support version bruteforce (UInt32 vs VInt protocol difference)
                self.main_window.reset_status_bar()
                return build_alert_box('Error', 'Server requires a different version. Please update major/build/minor in config.json.')

            # NOTE: unreachable from the current UI - "Latest Patch" is only
            # offered for servers that are not in `frozen_handshake_servers`,
            # and every Clash Royale host is listed there. The bruteforce is
            # kept (and hardened) for the day the CR handshake comes back.
            reply = QMessageBox.question(
                self, 'Warning', 'Can\'t fetch current info, build, major and minor from config are outdated. There was probably a game update, would you like to automatically update them ?', QMessageBox.Yes | QMessageBox.No)

            if reply == QMessageBox.Yes:
                self.update_client_hello_version()

            else:
                self.main_window.reset_status_bar()

            return

        if login_failed_error_code == 10:
            self.main_window.reset_status_bar()
            return build_alert_box('Error', 'Server is in maintenance, cannot fetch current info')

        self.main_window.reset_status_bar()
        return build_alert_box('Error', 'Wrong login failed code: {}'.format(login_failed_error_code))

    def parse_fingerprint(self, login_failed, is_cr):
        """Extract the fingerprint from a Loginfailed (error code 7) payload."""
        if is_cr:
            # === Clash Royale protocol (VInt-based) ===
            login_failed.read_string()

            login_failed.read_string()
            login_failed.read_string()
            login_failed.read_string()
            login_failed.read_vint()
            login_failed.read_vint()
            login_failed.read_string()

            assets_host_count = login_failed.read_vint()

            if not assets_host_count:
                return None

            for _ in range(assets_host_count):
                self.assets_host = login_failed.read_string()

            login_failed.read_string()
            login_failed.read_byte()

            return login_failed.read_compressed_string()

        # === Brawl Stars protocol (UInt32-based) ===
        login_failed.read_uint32()
        login_failed.read_uint32()

        self.assets_host = login_failed.read_string()

        login_failed.read_uint32()

        fingerprint = login_failed.read_string()

        # If fingerprint is None or empty, it's zlib-compressed (MySQL format)
        if not fingerprint:
            # Skip 5 zero bytes
            login_failed.seek(5, 1)

            compressed_data_length = login_failed.read_uint32()
            decompressed_data_length = unpack("<I", login_failed.read(4))[0]

            compressed_data = login_failed.read(compressed_data_length)
            decompressed_data = zlib.decompress(compressed_data)

            if len(decompressed_data) != decompressed_data_length:
                print('Data may be corrupted but we try to deserialize it anyway')

            fingerprint = decompressed_data.decode('utf8')

        # Also read assets_url and assets_url_2 for BS (in case content_url differs)
        # These are for future multi-CDN support
        _assets_url = login_failed.read_string()
        _assets_url_2 = login_failed.read_string()

        return fingerprint

    def on_masterhash_fetched(self, fingerprint, error):
        self.masterhash_fetcher_thread.quit()

        if error:
            self.main_window.reset_status_bar()
            return build_alert_box('Download error', 'Couldn\'t fetch any fingerprint for this masterhash ! ({})'.format(error))

        self.fingerprint = fingerprint
        self._on_fingerprint_ready()

    def _on_fingerprint_ready(self):
        if not is_fingerprint_valid(self.fingerprint):
            self.main_window.reset_status_bar()
            return build_alert_box('Invalid fingerprint', 'The fetched fingerprint is missing needed fields !')

        self.main_window.hide_loading()
        self.main_window.status_bar_label.setText('Fingerprint successfully fetched, version: {}'.format(
            self.fingerprint.get('version', 'unknown')))

        files_extension = []

        for file in self.fingerprint['files']:
            ext = os.path.splitext(file['file'])[1]

            if ext not in files_extension:
                files_extension.append(ext)

        self.start_button.setEnabled(False)
        self.download_method_combo_box.setEnabled(False)
        self.server_combo_box.setEnabled(False)

        download_choice_windows = DownloadChoiceWindow(self, files_extension)
        download_choice_windows.show()

    def request_login_failed(self):
        client_hello_writer = Writer()

        # Clash Royale requires its config version; Brawl Stars international
        # accepts 0; Brawl Stars CN requires a specific initial version.
        if self.selected_server_address in self.cr_protocol_hosts:
            major, build, minor = self.major, self.build, self.minor
        elif self.selected_server_address in self.server_version_overrides:
            major, build, minor = self.server_version_overrides[self.selected_server_address]
        else:
            major = build = minor = 0

        client_hello_writer.write_int(4)  # Updated from 3 to 4 after CR update
        client_hello_writer.write_int(27)
        client_hello_writer.write_int(major)
        client_hello_writer.write_int(build)
        client_hello_writer.write_int(minor)
        client_hello_writer.write_string('')
        client_hello_writer.write_int(2)
        client_hello_writer.write_int(2)

        client_hello = (10100).to_bytes(2, 'big') + len(client_hello_writer.buffer).to_bytes(3, 'big') + bytes(2) + client_hello_writer.buffer

        try:
            connection = socket.create_connection(
                (self.selected_server_address, SERVER_PORT), timeout=10)
            connection.settimeout(10)

            try:
                connection.sendall(client_hello)

                header = receive_exactly(connection, 7)

                if len(header) < 7:
                    return None

                message_length = int.from_bytes(header[2:5], 'big')
                login_failed = receive_exactly(connection, message_length)

                if len(login_failed) < message_length:
                    return None

            finally:
                connection.close()

            return Reader(login_failed)

        except (socket.timeout, TimeoutError, ConnectionError, OSError):
            return None

    def update_client_hello_version(self):
        self.start_button.setEnabled(False)
        self.download_method_combo_box.setEnabled(False)
        self.server_combo_box.setEnabled(False)

        self.main_window.show_loading()

        self.bruteforce_thread = UpdateClientHelloVersionThread(self)
        self.bruteforce_thread.values_found.connect(self.on_values_found)
        self.bruteforce_thread.progress.connect(self.on_bruteforce_progress)
        self.bruteforce_thread.failed.connect(self.on_bruteforce_failed)
        self.bruteforce_thread.start()

    def on_bruteforce_progress(self, major, build, minor):
        self.main_window.status_bar_label.setText(
            'Bruteforce started ! Trying with major {}, build {}, minor {}'.format(
                major, build, minor))

    def on_bruteforce_failed(self, message):
        self.bruteforce_thread.quit()

        self.main_window.reset_status_bar()

        self.start_button.setEnabled(True)
        self.download_method_combo_box.setEnabled(True)
        self.server_combo_box.setEnabled(True)

        build_alert_box('Bruteforce Error', message)

    def on_values_found(self):
        self.bruteforce_thread.quit()

        self.main_window.hide_loading()
        self.main_window.status_bar_label.setText(
            'Successfully bruteforced build, major and minor ! New major version: {}, new build version: {}, new minor version: {}'.format(
                self.major, self.build, self.minor))

        self.config['major'] = self.major
        self.config['build'] = self.build
        self.config['minor'] = self.minor

        self.main_window.save_config()

        self.start_button.setEnabled(True)
        self.download_method_combo_box.setEnabled(True)
        self.server_combo_box.setEnabled(True)

    def stop_download(self):
        """Ask the running download to stop.

        The launcher acknowledges every queued file before it exits, so the
        usual `download_finished` callback still drives the UI back to idle.
        """
        if self.worker_launcher is None:
            return

        self.download_cancelled = True
        self.stop_button.setEnabled(False)
        self.main_window.status_bar_label.setText('Stopping download...')

        self.worker_launcher.stop()

    def on_masterhash_changed(self, masterhash):
        if not masterhash:
            # Nothing typed yet - don't nag, `request_info` will complain.
            self.masterhash_validity_widget.hide()
            self.start_button.setEnabled(True)
            return

        valid = is_masterhash_valid(masterhash)

        self.masterhash_validity_widget.setVisible(not valid)
        self.start_button.setEnabled(valid)

    def start_download(self, wanted_extensions):
        self.downloaded_files = 0
        self.failed_files = 0
        self.download_cancelled = False
        self.download_start_time = time.monotonic()
        self.download_queue = Queue()

        # Let any previous run that is still winding down finish, but keep a
        # reference so Qt never destroys a running QThread.
        self.retired_launchers = [launcher for launcher in self.retired_launchers if launcher.isRunning()]

        if self.worker_launcher is not None and self.worker_launcher.isRunning():
            self.worker_launcher.stop()
            self.retired_launchers.append(self.worker_launcher)

        output_dir = join_path(self.main_window.settings_widget.output_path(), self.fingerprint['sha'])
        overwrite_existing_file = False

        self.workers_count = self.main_window.settings_widget.workers_spinbox.value()
        self.decompress_assets = self.enable_compression_checkbox.isChecked()
        self.output_dir = output_dir

        if os.path.isdir(output_dir):
            reply = QMessageBox.question(self, 'Warning', 'This patch was already downloaded, would you like to overwrite existing files ?', QMessageBox.Yes | QMessageBox.No)

            if reply == QMessageBox.Yes:
                overwrite_existing_file = True

        wanted_files = [file['file'] for file in self.fingerprint['files']
                        if file['file'].endswith(wanted_extensions)]

        # The manifest itself is always worth keeping next to the assets.
        if 'fingerprint.json' not in wanted_files:
            wanted_files.append('fingerprint.json')

        for filename in wanted_files:
            if overwrite_existing_file or not os.path.isfile(join_path(output_dir, filename)):
                self.download_queue.put(filename)

        self.total_files = self.download_queue.qsize()

        self.main_window.show_loading()

        self.worker_launcher = WorkerLauncher(self)

        self.worker_launcher.file_processed.connect(self.on_file_processed)
        self.worker_launcher.download_finished.connect(self.on_download_finish)

        self.worker_launcher.start()

    def on_file_processed(self, succeeded):
        if succeeded:
            self.downloaded_files += 1
        else:
            self.failed_files += 1

        processed = self.downloaded_files + self.failed_files

        if self.total_files:
            self.progress_bar.setValue(int(processed / self.total_files * 100))

        self.main_window.status_bar_label.setText(
            'Download started with {} workers, {}/{} files processed, {} failed !'.format(
                self.workers_count, processed, self.total_files, self.failed_files))

    def on_download_finish(self):
        self.main_window.hide_loading()
        self.download_method_combo_box.setEnabled(True)
        self.server_combo_box.setEnabled(True)

        elapsed_time = int(time.monotonic() - self.download_start_time) if self.download_start_time else 0

        if self.downloaded_files or self.failed_files:
            summary = '{}{} files downloaded'.format(
                'Download stopped ! ' if self.download_cancelled else 'Download finished ! ',
                self.downloaded_files)

            if self.failed_files:
                summary += ', {} failed (see the console for details)'.format(self.failed_files)

            summary += ' in {}min {}s'.format(*divmod(elapsed_time, 60))

            self.main_window.status_bar_label.setText(summary)

        else:
            self.main_window.status_bar_label.setText('No files were downloaded !')

        self.progress_bar.reset()
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(True)

    def shutdown_downloads(self):
        """Stop every download thread and wait for it, so the app can exit cleanly."""
        launchers = [launcher for launcher in [self.worker_launcher] + self.retired_launchers
                     if launcher is not None]

        for launcher in launchers:
            if launcher.isRunning():
                launcher.stop()

        for launcher in launchers:
            if launcher.isRunning():
                launcher.wait(30000)


class InfoFetcherThread(QThread):
    info_fetched = pyqtSignal(object)

    def __init__(self, parent):
        super().__init__()
        self.parent = parent

    def run(self):
        try:
            login_failed = self.parent.request_login_failed()
        except Exception as e:
            # An exception escaping run() would abort the whole process.
            print('[x] Could not reach {}: {}'.format(self.parent.selected_server_address, e))
            login_failed = None

        self.info_fetched.emit(login_failed)


class MasterhashFetcherThread(QThread):
    fingerprint_fetched = pyqtSignal(object, str)

    def __init__(self, parent, masterhash):
        super().__init__()
        self.parent = parent
        self.masterhash = masterhash

    def run(self):
        url = self.parent.assets_host + '/' + self.masterhash + '/fingerprint.json'

        try:
            with urlopen(url, timeout=30) as f:
                fingerprint = json.loads(f.read())

            self.fingerprint_fetched.emit(fingerprint, '')

        except HTTPError as e:
            self.fingerprint_fetched.emit(None, 'HTTP {}'.format(e.code))

        except Exception as e:
            self.fingerprint_fetched.emit(None, str(e))


class UpdateClientHelloVersionThread(QThread):
    """Recover the client version accepted by the server (binary search).

    NOTE: this path is currently unreachable from the UI, because "Latest
    Patch" is hidden for every server whose handshake is frozen and Brawl
    Stars does not support the bruteforce. It is kept - and hardened - for the
    day the Clash Royale handshake works again.
    """

    values_found = pyqtSignal()
    progress = pyqtSignal(int, int, int)
    failed = pyqtSignal(str)

    MAX_MAJOR_OFFSET = 200
    MAX_BUILD = 20000
    MAX_MINOR = 100

    def __init__(self, parent):
        super().__init__()
        self.parent = parent

    def request_error_code(self):
        """Send a ClientHello and return the Loginfailed error code.

        Returns ``None`` (after reporting the failure) when the server cannot
        be reached, so callers can stop instead of blowing up a worker thread.
        """
        login_failed = self.parent.request_login_failed()

        if login_failed is None:
            self.failed.emit('Lost the connection to the server during the version bruteforce.')
            return None

        return login_failed.read_vint()

    def run(self):
        try:
            self.bruteforce()
        except Exception as e:
            # An exception escaping run() would abort the whole process.
            self.failed.emit('Version bruteforce failed unexpectedly: {}'.format(e))

    def bruteforce(self):
        parent = self.parent

        major_found = False
        build_found = False
        minor_found = False

        build = parent.build
        major_limit = parent.major + self.MAX_MAJOR_OFFSET

        # Check major first with build & minor set to 0 so we avoid getting
        # an error code 9 due to too high build or minor instead of too high major
        parent.build = 0
        parent.minor = 0

        while not major_found:
            parent.major += 1

            if parent.major > major_limit:
                self.failed.emit('Could not find a valid major version (tested up to {}).'.format(major_limit))
                return

            self.progress.emit(parent.major, parent.build, parent.minor)
            error_code = self.request_error_code()

            if error_code is None:
                return

            major_found = error_code == 9

        parent.major -= 1
        parent.build = build

        error_code = self.request_error_code()

        if error_code is None:
            return

        if error_code == 9:
            parent.build = 0

        # Dichotomic search to speed up the process
        build_low, build_high = parent.build, self.MAX_BUILD

        while not build_found:
            parent.build = (build_low + build_high) // 2

            self.progress.emit(parent.major, parent.build, parent.minor)
            error_code = self.request_error_code()

            if error_code is None:
                return

            if error_code == 7:
                build_low = parent.build + 1
                break

            elif error_code in (8, 16):
                build_low = parent.build + 1

            elif error_code == 9:
                build_high = parent.build - 1

            else:
                self.failed.emit(
                    'Unexpected login failed error code during bruteforce '
                    '(major={}, build={}, minor={}): {}'.format(
                        parent.major, parent.build, parent.minor, error_code))
                return

            build_found = build_low > build_high or (build_low + build_high) // 2 == parent.build

        parent.build = max(build_low - 1, 0)

        while not minor_found:
            self.progress.emit(parent.major, parent.build, parent.minor)
            error_code = self.request_error_code()

            if error_code is None:
                return

            minor_found = error_code == 7
            parent.minor += 1

            if parent.minor > self.MAX_MINOR:
                self.failed.emit(
                    'Could not find a valid minor version (tested up to {}). '
                    'Last error code: {}'.format(self.MAX_MINOR, error_code))
                return

        parent.minor -= 1
        self.values_found.emit()
