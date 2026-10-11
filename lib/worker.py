import os
import time
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from PyQt5.QtCore import QThread, pyqtSignal

from lib.utils import join_path
from lib.compression import decompress


class DownloadWorker(QThread):

    #: Emitted once per processed file. ``True`` means the file was written,
    #: ``False`` means it failed.
    file_processed = pyqtSignal(bool)

    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds, doubled after every retry
    RETRYABLE_HTTP_CODES = (502, 503, 504)

    def __init__(self, download_queue,
                 masterhash, assets_url,
                 decompress_data, output_dir):

        super().__init__()

        self.assets_url = assets_url
        self.masterhash = masterhash
        self.output_dir = output_dir
        self.download_queue = download_queue
        self.decompress_data = decompress_data

        #: Set by :meth:`stop`. The worker keeps draining the queue so every
        #: ``get()`` still gets a matching ``task_done()`` - otherwise
        #: ``Queue.join()`` would block forever.
        self.stopped = False

    def run(self):
        while True:
            filename = self.download_queue.get()

            try:
                if filename is None:
                    return

                if self.stopped:
                    continue

                succeeded = False

                try:
                    succeeded = self.download_file(filename)
                except Exception as e:
                    # Nothing may escape run(): PyQt aborts the whole process
                    # when a QThread override raises.
                    print('[x] Failed to download {} - Unexpected error: {}'.format(filename, e))

                self.file_processed.emit(succeeded)
            finally:
                self.download_queue.task_done()

    def download_file(self, filename):
        file_url = join_path(self.assets_url, self.masterhash, filename)
        destination = join_path(self.output_dir, filename)

        retry_delay = self.RETRY_DELAY

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = urlopen(file_url, timeout=30)

                try:
                    content = self.read_content(response, filename)
                finally:
                    response.close()

                write_file(destination, content)
                return True

            except HTTPError as e:
                if e.code in self.RETRYABLE_HTTP_CODES and attempt < self.MAX_RETRIES:
                    print('[!] HTTP {} for {}, retrying in {}s (attempt {}/{})'.format(
                        e.code, filename, retry_delay, attempt, self.MAX_RETRIES))
                    if self.sleep(retry_delay):
                        retry_delay *= 2
                else:
                    print('[x] Failed to download {} - HTTP Error {}: {}'.format(
                        filename, e.code, e.reason))
                    return False

            except URLError as e:
                if attempt < self.MAX_RETRIES:
                    print('[!] Network error for {}, retrying in {}s (attempt {}/{})'.format(
                        filename, retry_delay, attempt, self.MAX_RETRIES))
                    if self.sleep(retry_delay):
                        retry_delay *= 2
                else:
                    print('[x] Failed to download {} - Network Error: {}'.format(
                        filename, e.reason))
                    return False

            except Exception as e:
                print('[x] Failed to download {} - Unexpected error: {}'.format(filename, e))
                return False

        return False

    def read_content(self, response, filename):
        if self.decompress_data and filename.endswith(('.csv', '.sc', '.toml')):
            compressed_data = response.read()

            try:
                return decompress(compressed_data)
            except Exception as e:
                print('[x] Failed to decompress {} ({}), keeping the compressed data'.format(
                    filename, e))
                return compressed_data

        return response.read()

    def sleep(self, seconds):
        """Sleep, unless the worker was asked to stop. Returns False on stop."""
        if self.stopped:
            return False

        time.sleep(seconds)
        return not self.stopped

    def stop(self):
        """Ask this worker to stop.

        It finishes the file it is currently working on and then discards the
        remaining queue entries (still acknowledging them), so the launcher's
        ``Queue.join()`` can return.
        """
        self.stopped = True


def write_file(destination, content):
    """Write ``content`` to ``destination`` without leaving partial files behind."""
    directory = os.path.dirname(destination)

    if directory:
        os.makedirs(directory, exist_ok=True)

    temp_path = destination + '.part'

    try:
        with open(temp_path, 'wb') as f:
            f.write(content)

        os.replace(temp_path, destination)

    except BaseException:
        remove_quietly(temp_path)
        raise


def remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
