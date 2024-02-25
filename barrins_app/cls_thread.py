import threading


class DaemonThread(threading.Thread):
    """Thread with daemon attribute set to True."""

    def __init__(self, *args, **kwargs):
        super(DaemonThread, self).__init__(*args, **kwargs)
        self.daemon = True
