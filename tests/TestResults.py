#
# Copyright (C) 2025 CEA
#
import textwrap
import xml.etree.ElementTree as ET
from io import BytesIO

from TestUtils import RiftTestCase
from rift.TestResults import TestResults, TestCase

class TestResultsTest(RiftTestCase):
    """
    Tests class for TestResults
    """

    def test_init(self):
        """ TestResults instance """
        results = TestResults()

        self.assertCountEqual(results.results, [])
        self.assertTrue(results.global_result)
        self.assertEqual(len(results), 0)

    def test_add_success(self):
        results = TestResults()
        results.add_success(TestCase('test1', 'pkg', 'x86_64'), 1)
        results.add_success(TestCase('test2', 'pkg', 'x86_64'), 1)
        self.assertTrue(results.global_result)
        self.assertEqual(len(results), 2)

    def test_add_failure(self):
        results = TestResults()
        results.add_failure(TestCase('test1', 'pkg', 'x86_64'), 1)
        results.add_failure(TestCase('test2', 'pkg', 'x86_64'), 1)
        self.assertFalse(results.global_result)
        self.assertEqual(len(results), 2)

    def test_add_success_failure(self):
        results = TestResults()
        results.add_success(TestCase('test1', 'pkg', 'x86_64'), 1)
        results.add_failure(TestCase('test2', 'pkg', 'x86_64'), 1)
        self.assertFalse(results.global_result)
        self.assertEqual(len(results), 2)

    def test_extend(self):
        results = TestResults()
        results.add_success(TestCase('test1', 'pkg1', 'x86_64'), 1)
        results.add_failure(TestCase('test2', 'pkg1', 'x86_64'), 1)
        others = TestResults()
        others.add_success(TestCase('test1', 'pkg2', 'x86_64'), 1)
        others.add_failure(TestCase('test2', 'pkg2', 'x86_64'), 1)
        results.extend(others)
        self.assertFalse(results.global_result)
        self.assertEqual(len(results), 4)

    def test_junit(self):
        results = TestResults()
        results.add_success(TestCase('test1', 'pkg', 'x86_64'), 1, out="output test1")
        results.add_failure(TestCase('test2', 'pkg', 'x86_64'), 1, out="output test2")
        output = BytesIO()
        results.junit(output)
        root = ET.fromstring(output.getvalue().decode())
        self.assertEqual(root.tag, 'testsuite')
        self.assertEqual(root.attrib, { 'tests': '2'})
        self.assertEqual(len(root.findall('*')), 2)
        for element in root:
            self.assertEqual(element.tag, 'testcase')
            self.assertIn(element.attrib['name'], ['test1', 'test2'])
            self.assertEqual(element.attrib['classname'], 'rift.pkg')
            self.assertEqual(element.attrib['time'], '1.00')
            if element.attrib['name'] == 'test1':
                self.assertIsNone(element.find('failure'))
                self.assertEqual(element.find('system-out').text, 'output test1')
            else:
                self.assertIsNotNone(element.find('failure'))
                self.assertEqual(element.find('system-out').text, 'output test2')

    def test_summary(self):
        results = TestResults()
        results.add_success(TestCase('test1', 'pkg', 'x86_64'), 1)
        results.add_failure(TestCase('test2', 'pkg', 'x86_64'), 1)
        self.assertEqual(
            results.summary(),
            textwrap.dedent(
                """\
                NAME      ARCH   DURATION RESULT
                ----      ----   -------- ------
                pkg.test1 x86_64       1s Success
                pkg.test2 x86_64       1s FAILURE"""
            )
        )
