# coding=utf-8
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Run a subprocess with timeout
"""

import argparse
import collections
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

(CRASHED, TIMED_OUT, NORMAL, ABNORMAL, NONE) = range(5)


# Define struct that contains data from a process that has already ended.
RunData = collections.namedtuple(
    "RunData",
    "sta, return_code, msg, elapsedtime, killed, out, err",
)


class ArgumentParser(argparse.ArgumentParser):
    """Argument parser with `timeout` and `cmd_with_args`"""

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.add_argument(
            "-t",
            "--timeout",
            default=120,
            dest="timeout",
            type=int,
            help="Set the timeout. Defaults to '%(default)s' seconds.",
        )
        self.add_argument("cmd_with_flags", nargs=argparse.REMAINDER)


def get_signal_name(signum, default="Unknown signal"):
    """Stringify a signal number. The result will be something like "SIGSEGV",
    or from Python 3.8, "Segmentation fault".

    Args:
        signum (int): Signal number to lookup
        default (str): Default to return if signal isn't recognized.

    Returns:
        str: String description of the signal.
    """
    if sys.version_info[:2] >= (3, 8) and platform.system() != "Windows":
        return signal.strsignal(signum) or default
    for member in dir(signal):
        if member.startswith("SIG") and not member.startswith("SIG_"):
            if getattr(signal, member) == signum:
                return member
    return default


def timed_run(cmd_with_args, timeout, log_prefix=None, env=None, inp=None):
    """If log_prefix is None, uses pipes instead of files for all output.

    Args:
        cmd_with_args (list): List of command and parameters to be executed
        timeout (int): Timeout for the command to be run, in seconds
        log_prefix (str): Prefix string of the log files
        env (dict): Environment for the command to be executed in
        inp (str): stdin to be passed to the command

    Raises:
        TypeError: Raises if input parameters are not of the desired types
                   (e.g. cmd_with_args should be a list)
        OSError: Raises if timed_run is attempted to be used with gdb

    Returns:
        class: A rundata instance containing run information
    """
    if not isinstance(cmd_with_args, list):
        raise TypeError("cmd_with_args should be a list (of strings).")
    if not isinstance(timeout, int):
        raise TypeError("timeout should be an int.")
    if log_prefix is not None and not isinstance(log_prefix, str):
        raise TypeError("log_prefix should be a string.")

    prog = Path(cmd_with_args[0]).expanduser()
    cmd_with_args[0] = str(prog)

    if prog.stem == "gdb":
        raise OSError(
            "Do not use this with gdb, because kill in timed_run will "
            "kill gdb but leave the process within gdb still running"
        )

    sta = NONE
    msg = ""

    child_stdout = child_stderr = subprocess.PIPE
    if log_prefix is not None:
        child_stdout = open(log_prefix + "-out.txt", "wb")
        child_stderr = open(log_prefix + "-err.txt", "wb")

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd_with_args,
            env=env,
            input=inp,
            stderr=child_stderr,
            stdout=child_stdout,
            timeout=timeout,
        )
    except subprocess.SubprocessError as exc:
        if not isinstance(exc, subprocess.TimeoutExpired):
            print("Tried to run:")
            print("  %r" % cmd_with_args)
            print("but got this error:")
            print("  %s" % exc)
            sys.exit(2)
        sta = TIMED_OUT
        result = exc  # needed for stdout/stderr
    finally:
        if log_prefix is not None:
            child_stdout.close()
            child_stderr.close()
    elapsed_time = time.time() - start_time

    if sta == TIMED_OUT:
        msg = "TIMED OUT"
    elif result.returncode == 0:
        msg = "NORMAL"
        sta = NORMAL
    elif 0 < result.returncode < 0x80000000:
        msg = "ABNORMAL exit code " + str(result.returncode)
        sta = ABNORMAL
    else:
        # return_code < 0 (or > 0x80000000 in Windows)
        # The program was terminated by a signal, which usually indicates a crash.
        # Mac/Linux only!
        # XXX: this doesn't work on Windows
        if result.returncode < 0:
            signum = -result.returncode
        else:
            signum = result.returncode
        msg = "CRASHED signal %d (%s)" % (
            signum,
            get_signal_name(signum),
        )
        sta = CRASHED

    return RunData(
        sta,
        getattr(result, "returncode", None),  # result might be TimeoutExpired
        msg,
        elapsed_time,
        sta == TIMED_OUT,
        log_prefix + "-out.txt" if log_prefix is not None else result.stdout,
        log_prefix + "-err.txt" if log_prefix is not None else result.stderr,
    )
