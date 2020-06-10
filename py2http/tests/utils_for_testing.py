from contextlib import contextmanager


@contextmanager  # see https://docs.python.org/3/library/contextlib.html#contextlib.contextmanager
def run_server(launcher, wait_before_entering=0.5, **kwargs):
    """Context manager to launch server on entry, and shut it down on exit"""
    from multiprocessing.context import Process
    from time import sleep
    server = None
    try:
        server = Process(target=launcher, kwargs=kwargs)
        server.start()
        sleep(wait_before_entering)
        yield server
    finally:
        if server is not None:
            server.terminate()
