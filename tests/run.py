#
# Copyright (C) 2024 CEA
#

from io import StringIO
from unittest.mock import patch

from .TestUtils import RiftTestCase
from rift.run import RunResult, run_command

class RunTest(RiftTestCase):
    """
    Tests class for run_command
    """

    def test_run_command(self):
        """ Test run_command() with basic successful command. """
        proc = run_command(["/bin/true"])
        self.assertIsInstance(proc, RunResult)
        self.assertEqual(proc.returncode, 0)
        self.assertIsNone(proc.out)
        self.assertIsNone(proc.err)

    def test_run_command_failed(self):
        """ Test run_command() with basic failed command. """
        proc = run_command(["/bin/false"])
        self.assertEqual(proc.returncode, 1)
        self.assertIsNone(proc.out)
        self.assertIsNone(proc.err)

    @patch('sys.stdout', new_callable=StringIO)
    def test_run_command_capture_stdout(self, mock_stdout):
        """ Test run_command() with captured standard output. """
        proc = run_command(["/bin/echo", "output_data"], capture_output=True)
        # Standard output must be available in out attribute of RunResult named
        # tuple.
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.out, "output_data\n")
        self.assertEqual(proc.err, "")
        # Standard output must also be streamed into current process stdout.
        self.assertEqual(mock_stdout.getvalue(), "output_data\n")

    @patch('sys.stderr', new_callable=StringIO)
    def test_run_command_capture_stderr(self, mock_stderr):
        """ Test run_command() with captured standard error. """
        proc = run_command("/bin/echo error_data 1>&2", capture_output=True, shell=True)
        # Standard err must be available in err attribute of RunResult named
        # tuple.
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.out, "")
        self.assertEqual(proc.err, "error_data\n")
        # Standard error must also be streamed into current process stderr.
        self.assertEqual(mock_stderr.getvalue(), "error_data\n")

    @patch('sys.stderr', new_callable=StringIO)
    def test_run_command_capture_stderr_merged(self, mock_stderr):
        """ Test run_command() with merged error output capture. """
        proc = run_command("/bin/echo error_data 1>&2", capture_output=True,
                merge_out_err=True, shell=True)
        # With merged_capture, standard err must be available in out attribute
        # of RunResult named tuple, and err attribute must be None.
        self.assertEqual(proc.out, "error_data\n")
        self.assertIsNone(proc.err)
        # Standard error must also be streamed into current process stderr.
        self.assertEqual(mock_stderr.getvalue(), "error_data\n")

    @patch('sys.stderr', new_callable=StringIO)
    def test_run_command_capture_both_merged(self, mock_stderr):
        """ Test run_command() with merged error and standard output capture. """
        proc = run_command("/bin/echo error_data 1>&2 && /bin/echo output_data",
                capture_output=True, merge_out_err=True, shell=True)
        # With merge_out_err, standard err must be available in out attribute
        # of RunResult named tuple, and err attribute must be None.
        self.assertEqual(proc.out, "error_data\noutput_data\n")
        self.assertIsNone(proc.err)
        # Standard error must also be streamed into current process stderr.
        self.assertEqual(mock_stderr.getvalue(), "error_data\n")

    @patch('sys.stderr', new_callable=StringIO)
    @patch('sys.stdout', new_callable=StringIO)
    def test_run_command_no_output(self, mock_stdout, mock_stderr):
        """ Test run_command() without live output. """
        # With live_output disabled, standard output and standard error must not
        # be redirected in current process stdout.
        proc = run_command(["/bin/echo", "output_data"], live_output=False)
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertEqual(mock_stderr.getvalue(), "")
