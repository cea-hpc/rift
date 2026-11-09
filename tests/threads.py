#
# Copyright (C) 2026 CEA
#
from unittest.mock import Mock

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
