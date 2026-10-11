import os
import time
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from PyQt5.QtCore import QThread, pyqtSignal

from lib.utils import join_path
from lib.compression import decompress


class DownloadWorker(QThread):

    file_downloaded = pyqtSignal(bool)

    def __init__(self, download_queue,
                 masterhash, assets_url,
                 decompress_data, output_dir):

        self.stopped = False
        self.is_running = True

        self.assets_url = assets_url
        self.masterhash = masterhash
        self.output_dir = output_dir
        self.download_queue = download_queue
        self.decompress_data = decompress_data

        QThread.__init__(self)

    def run(self):
        while self.is_running:
            filename = self.download_queue.get()

            if filename is not None:
                file_url = join_path(self.assets_url, self.masterhash, filename)

                # Retry logic for transient errors
                max_retries = 3
                retry_delay = 1  # seconds

                for attempt in range(max_retries):
                    try:
                        file_data = urlopen(file_url, timeout=30)

                        os.makedirs(os.path.dirname(join_path(self.output_dir, filename)), exist_ok=True)

                        with open(join_path(self.output_dir, filename), 'wb') as f:
                            if self.decompress_data and filename.endswith(('.csv', '.sc', '.toml')):
                                compressed_data = file_data.read()

                                try:
                                    decompressed = decompress(compressed_data)

                                except:
                                    print('[x] Failed to decompress file {}'.format(filename))
                                    decompressed = compressed_data

                                f.write(decompressed)

                            else:
                                f.write(file_data.read())

                            f.close()

                        self.file_downloaded.emit(self.is_running)
                        break  # Success, exit retry loop

                    except HTTPError as e:
                        # Retry on server errors (502, 503, 504)
                        if e.code in [502, 503, 504] and attempt < max_retries - 1:
                            print('[!] HTTP {} for {}, retrying in {}s (attempt {}/{})'.format(
                                e.code, filename, retry_delay, attempt + 1, max_retries))
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            print('[x] Failed to download {} - HTTP Error {}: {}'.format(
                                filename, e.code, e.reason))
                            break

                    except URLError as e:
                        if attempt < max_retries - 1:
                            print('[!] Network error for {}, retrying in {}s (attempt {}/{})'.format(
                                filename, retry_delay, attempt + 1, max_retries))
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            print('[x] Failed to download {} - Network Error: {}'.format(filename, e.reason))
                            break

                    except Exception as e:
                        print('[x] Failed to download {} - Unexpected error: {}'.format(filename, str(e)))
                        break

            self.download_queue.task_done()

    def stop(self):
        self.download_queue.put(None)
        self.is_running = False
