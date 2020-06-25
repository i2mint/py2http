from contextlib import contextmanager

def conditional_logger(verbose=False):
    if verbose:
        clog = print
    else:
        def clog(*args, **kwargs):
            pass  # do nothing
    return clog

@contextmanager  # see https://docs.python.org/3/library/contextlib.html#contextlib.contextmanager
def run_server(launcher, wait_before_entering=0.5, verbose=False, **kwargs):
    """Context manager to launch server on entry, and shut it down on exit"""
    from multiprocessing.context import Process
    from time import sleep
    clog = conditional_logger(verbose)
    server = None
    try:
        server = Process(target=launcher, kwargs=kwargs)
        server.start()
        clog(f"Server starting")
        sleep(wait_before_entering)
        yield server
    finally:
        if server is not None:
            server.terminate()
        clog(f"Server stopped")
