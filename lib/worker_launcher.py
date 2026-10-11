from PyQt5.QtCore import QThread, pyqtSignal

from lib.worker import DownloadWorker


class WorkerLauncher(QThread):

    #: Forwarded from the underlying workers.
    file_processed = pyqtSignal(bool)
    download_finished = pyqtSignal()

    def __init__(self, download_widget):
        super().__init__()

        self.download_widget = download_widget
        self.thread_list = []

    def run(self):
        widget = self.download_widget

        # Everything the workers need was snapshotted on the GUI thread before
        # this thread was started.
        for _ in range(widget.workers_count):
            worker = DownloadWorker(widget.download_queue,
                                    widget.fingerprint['sha'],
                                    widget.assets_host,
                                    widget.decompress_assets,
                                    widget.output_dir)

            worker.file_processed.connect(self.file_processed)
            self.thread_list.append(worker)
            worker.start()

        try:
            # Returns once every queued file has been acknowledged, either
            # because it was downloaded or because the run was cancelled.
            widget.download_queue.join()
        finally:
            self.shutdown_workers()

        self.download_finished.emit()

    def shutdown_workers(self):
        """Wake the workers up once every task has been accounted for."""
        download_queue = self.download_widget.download_queue

        for _ in self.thread_list:
            download_queue.put(None)

        for worker in self.thread_list:
            worker.wait()

    def stop(self):
        """Cancel the current run without breaking the queue bookkeeping."""
        for worker in self.thread_list:
            worker.stop()
