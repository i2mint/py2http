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
        clog(f"Starting server...")
        server.start()
        clog(f"... server started.")
        sleep(wait_before_entering)
        yield server
    finally:
        if server is not None and server.is_alive():
            clog(f"Terminating server...")
            server.terminate()
        clog(f"... server terminated")


from typing import Callable, Union, Any
from time import sleep, time


def launch_and_wait_till_ready(start_process: Callable[[], Any],
                               is_ready: Union[Callable[[], Any], float, int] = 5.0,
                               check_every_seconds=1.0, timeout=30.0):
    """A function that launches a process, checks if it's ready, and exits when it is.

    :param start_process: A argument-less function that launches an independent process
    :param is_ready: A argument-less function that returns False if, and only if, the process should be considered ready
    :param check_every_seconds: Determines the frequency that is_ready will be called
    :param timeout: Determines how long to wait for the process to be ready before we should give up
    :return: start_process_output, is_ready_output
    """
    start_time = time()

    # If is_ready is a number, make an is_ready function out of it
    if isinstance(is_ready, (float, int)):
        is_ready_in_seconds = is_ready

        def is_ready():
            f"""Returns True if, and only if, {is_ready_in_seconds} elapsed"""
            return time() - start_time >= is_ready_in_seconds

        is_ready.__name__ = f"wait_for_seconds({is_ready_in_seconds})"
    start_process_output = start_process()  # needs launch a parallel process!
    while time() - start_time < timeout:
        tic = time()
        is_ready_output = is_ready()
        if is_ready_output is False:
            elapsed = time() - tic
            sleep(max(0, check_every_seconds - elapsed))
        else:
            return start_process_output, is_ready_output
    # If you got so far, raise TimeoutError
    name_of = lambda o: getattr(o, '__qualname__', None)
    raise TimeoutError(f"Launching {name_of(start_process)} "
                       f"and checking for readiness with {name_of(is_ready)} "
                       f"timedout (timeout={timeout}s)")


@contextmanager
@deprecate
def run_process(launcher, is_ready=2, verbose=False, timeout=30, **kwargs):
    """Context manager to launch server on entry, and shut it down on exit"""
    from warnings import warn
    process_name = getattr(launcher, '__name__', '\b')
    clog = conditional_logger(verbose)
    process = None
    try:
        process = Process(target=launcher, kwargs=kwargs)

        def process_launcher():
            clog(f"Starting {process_name} process...")
            process.start()
            clog(f"... {process_name} process started.")

        # launch the process and wait until it's ready
        launch_and_wait_till_ready(process_launcher, is_ready, timeout=timeout)
        # when ready, return the process object
        yield process
    finally:
        if process is not None and process.is_alive():
            clog(f"Terminating {process_name} process...")
            process.terminate()
        clog(f"... {process_name} process terminated")
