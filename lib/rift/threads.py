#
# Copyright (C) 2026 CEA
#
# This file is part of Rift project.
#
# This software is governed by the CeCILL license under French law and
# abiding by the rules of distribution of free software.  You can  use,
# modify and/ or redistribute the software under the terms of the CeCILL
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and  rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty  and the software's author,  the holder of the
# economic rights,  and the successive licensors  have only  limited
# liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading,  using,  modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean  that it is complicated to manipulate,  and  that  also
# therefore means  that it is reserved for developers  and  experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systems and/or
# data to be ensured and,  more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.
#

"""Threads classes and utilities to build for architectures in parallel."""

import sys
import threading
import contextlib
import traceback
import io

from rift.TestResults import TestResults


# Python provides standards context managers contextlib.redirect_{stdout,stderr}
# but they are not thread-safe unfortunately. For redirecting threads
# stdout/stderr in a buffer, Rift uses a combination of:
#
# - stdout/stderr proxy that tries to use thread local stream before fallback to
#   default process stdout/stderr
# - thread-safe context manager which sets up a thread local stream.

class _ThreadLocalStream:
    """Rift stdout/stderr proxies, to support threads local buffering."""
    def __init__(self, default):
        # Store the original global stream (real sys.stdout / sys.stderr)
        self._default = default

        # Thread-local storage: each thread gets its own independent "stream"
        self.local = threading.local()

    def write(self, data):
        """
        Write data to stream. First look up the stream for the current thread.
        If none is set, fall back to the original global stream.
        """
        stream = getattr(self.local, "stream", self._default)

        # Delegate the write to the selected stream
        stream.write(data)

    def flush(self):
        """
        Flush stream. First look up the stream for the current thread. If none
        is set, fall back to the original global stream.
        """
        stream = getattr(self.local, "stream", self._default)

        # Delegate flush to that stream
        stream.flush()


def _install_proxy():
    """Install stdout/stderr proxies if not installed yet."""
    if not isinstance(sys.stdout, _ThreadLocalStream):
        sys.stdout = _ThreadLocalStream(sys.stdout)

    if not isinstance(sys.stderr, _ThreadLocalStream):
        sys.stderr = _ThreadLocalStream(sys.stderr)


# Install stdout/stderr proxies at import time so logging handlers can use them
# as soon as they are initialized.
_install_proxy()


@contextlib.contextmanager
def redirect_output_threadsafe(output):
    """
    Temporarily redirect stdout and/or stderr for the current thread only.

    Unlike contextlib.redirect_stdout, this does NOT modify global sys.stdout.
    Instead, it sets a thread-local override used by our proxy streams.
    """

    # Make sure stdout/stderr proxies are installed
    _install_proxy()

    # Set provided output stream for local thread
    sys.stdout.local.stream = sys.stderr.local.stream = output

    try:
        # Execute the block with redirected output
        yield
    finally:
        # Remove thread local attributes to fall back to default stdout/stderr
        del sys.stdout.local.stream
        del sys.stderr.local.stream


class RiftThread(threading.Thread):
    """Base thread for Rift parallel processing"""
    def __init__(self, target, name, args):
        # Initializing the Thread class
        super().__init__(None, target, name, args=args)
        self.output = io.StringIO()   # output buffer, for stdout/stderr
        self.results = TestResults()  # build/validate tests results

    def run(self):
        """
        Run the thread target and bufferize its stdout/stderr in output attribute.
        """
        with redirect_output_threadsafe(self.output):
            try:
                self.results = self._target(*self._args)
            except Exception:
                # Avoid threading.Thread to catch the Exception and report the
                # stacktrace out of thread buffered output. Force print of
                # exception in sys.stderr here to make it land in thread local
                # buffer.
                traceback.print_exc(file=sys.stderr)
