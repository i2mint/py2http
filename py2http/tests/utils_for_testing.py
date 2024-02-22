from contextlib import contextmanager
from multiprocessing.context import Process
from time import sleep
from py2http.util import conditional_logger, deprecate


@contextmanager
@deprecate
def run_server(launcher, wait_before_entering=0, verbose=False, **kwargs):
    """Context manager to launch server on entry, and shut it down on exit"""
    from warnings import warn

    clog = conditional_logger(verbose)
    server = None
    try:
        server = Process(target=launcher, kwargs=kwargs)
        clog(f'Starting server...')
        server.start()
        clog(f'... server started.')
        sleep(wait_before_entering)
        yield server
    finally:
        if server is not None and server.is_alive():
            clog(f'Terminating server...')
            server.terminate()
        clog(f'... server terminated')
