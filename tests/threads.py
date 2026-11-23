#
# Copyright (C) 2026 CEA
#
from io import StringIO
from unittest.mock import Mock, patch

from rift import RiftError
from rift.test_results import TestResults
from rift.threads import Job, RiftThread

from .test_utils import RiftTestCase


class JobTest(RiftTestCase):
    """Tests class for Job"""

    def test_name(self):
        """Test Job name"""
        job = Job("build", Mock(), Mock(), Mock(), "x86_64", "main")
        self.assertEqual(job.name, "build-x86_64-main")

    def test_run(self):
        """Test Job run calls worker with its context and returns its results"""
        results = TestResults()
        worker = Mock(return_value=results)
        args = Mock()
        pkg = Mock()
        staging = Mock()
        job = Job("build", worker, args, pkg, "x86_64", "main", staging)
        self.assertIs(job.run(), results)
        worker.assert_called_once_with(args, pkg, "x86_64", staging, "main")

    @patch("sys.stderr", new_callable=StringIO)
    def test_run_crash(self, mock_stderr):
        """Test Job run reports worker crash as failure with traceback"""
        worker = Mock(side_effect=RiftError("fail"))
        pkg = Mock()
        pkg.name = "pkg"
        pkg.format = "rpm"
        job = Job("build", worker, Mock(), pkg, "x86_64", "main")
        results = job.run()
        self.assertFalse(results.global_result)
        self.assertEqual(len(results), 1)
        result = results.results[0]
        self.assertEqual(result.value, "Failure")
        self.assertEqual(result.case.name, "build")
        self.assertEqual(result.case.classname, "pkg")
        self.assertEqual(result.case.arch, "x86_64")
        self.assertEqual(result.case.variant, "main")
        self.assertEqual(result.case.format, "rpm")
        self.assertEqual(result.err, "fail")
        self.assertIn("rift.RiftError: fail", mock_stderr.getvalue())


class RiftThreadTest(RiftTestCase):
    """Tests class for RiftThread"""

    def test_run_job(self):
        """Test RiftThread runs job, keeps its results and buffers its output"""
        results = TestResults()

        def worker(args, pkg, arch, staging, variant):
            print("worker output")
            return results

        job = Job("build", worker, Mock(), Mock(), "x86_64", "main")
        thread = RiftThread(job)
        self.assertEqual(thread.name, "build-x86_64-main")
        self.assertIs(thread.job, job)
        thread.start()
        thread.join()
        self.assertIs(thread.results, results)
        self.assertEqual(thread.output.getvalue(), "worker output\n")

    def test_run_job_crash(self):
        """Test RiftThread buffers traceback of crashed job and its failure"""

        def worker(args, pkg, arch, staging, variant):
            raise RiftError("fail")

        pkg = Mock()
        pkg.name = "pkg"
        pkg.format = "rpm"
        thread = RiftThread(Job("build", worker, Mock(), pkg, "x86_64", "main"))
        thread.start()
        thread.join()
        self.assertFalse(thread.results.global_result)
        self.assertIn("rift.RiftError: fail", thread.output.getvalue())
