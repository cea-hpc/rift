#
# Copyright (C) 2014-2016 CEA
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

import re
import collections
import xml.etree.cElementTree as ET

from rift.TextTable import TextTable

def str_xml_escape(arg):
    r"""Visually escape invalid XML characters.

    For example, transforms
        'hello\aworld\b'
    into
        'hello#x07world#x08'
    Note that the #xABs are *not* XML escapes - missing the ampersand &#xAB.
    The idea is to escape visually for the user rather than for XML itself.

    Initially based on:
    https://github.com/pytest-dev/pytest/blob/main/src/_pytest/junitxml.py
    """

    def repl(matchobj) -> str:
        i = ord(matchobj.group())
        if i <= 0xFF:
            return f"#x{i:02X}"
        return f"#x{i:04X}"

    # The spec range of valid chars is:
    # Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD]
    #          | [#x10000-#x10FFFF]
    # For an unknown(?) reason, we disallow #x7F (DEL) as well.
    illegal_xml_re = (
        "[^\u0009\u000a\u000d\u0020-\u007e\u0080-\ud7ff\ue000-\ufffd\u10000-"
        "\u10ffff]"
    )
    return re.sub(illegal_xml_re, repl, arg)


class TestCase():
    """
    TestCase: oject for to manage a Test to format ajunit file in TestResult
    """

    def __init__(self, name, classname, arch):
        """
        name: TestCase name
        classname: TestCase classname
        arch: TestCase CPU architecture
        """
        self.name = name
        self.classname = classname
        self.arch = arch

    @property
    def fullname(self):
        """
        return the TestCase fullname
        """
        if self.classname:
            return f"{self.classname}.{self.name}"
        return self.name


TestResult = collections.namedtuple(
    'TestResult', ['case', 'value', 'time', 'out', 'err']
)


class TestResults():
    """
    TestResults: gather and mange TestCase results
    """

    def __init__(self, name=None):
        """
        name: TestResults name
        properties:
            - results: list containing tests results
        """
        self.name = name
        self.results = []
        self.global_result = True

    def __len__(self):
        """
        return number of results
        """
        return len(self.results)

    def add_failure(self, case, time, out=None, err=None):
        """
        Add a failed TestCase
        """
        self._add_result(TestResult(case, 'Failure', time, out, err))
        self.global_result = False

    def add_success(self, case, time, out=None, err=None):
        """
        Add a successful TestCase
        """
        self._add_result(TestResult(case, 'Success', time, out, err))

    def _add_result(self, result):
        """
        Add a result from a TestCase
        """
        self.results.append(result)

    def extend(self, other):
        """
        Extend TestResults with all TestResult from the other TestResults.
        """
        for result in other.results:
            self.results.append(result)
            if result.value == 'Failure':
                self.global_result = False

    def junit(self, filename):
        """
        Generate a junit xml file containing all tests results.

        When result out property is defined, test outputs (out and err) are
        reported in <system-out/> and <system-err/> tags. When only result err
        property is defined, it is reported in <failure/> tag only when test is
        failed.
        """

        suite = ET.Element('testsuite', tests=str(len(self.results)))
        if self.name:
            suite.set('name', self.name)

        for result in self.results:
            sub = ET.SubElement(suite, 'testcase', name=result.case.name)
            if result.case.classname:
                sub.set('classname', f"rift.{result.case.classname}")
            if result.time:
                sub.set('time', f"{result.time:.2f}")
            if result.value == 'Failure':
                failure = ET.SubElement(sub, 'failure')
                if result.out is None and result.err:
                    failure.text = str_xml_escape(result.err)
            if result.out:
                system_out = ET.SubElement(sub, 'system-out')
                system_out.text = str_xml_escape(result.out)
                if result.err:
                    system_err = ET.SubElement(sub, 'system-err')
                    system_err.text = str_xml_escape(result.err)

        tree = ET.ElementTree(suite)
        tree.write(filename, encoding='UTF-8', xml_declaration=True)

    def summary(self):
        """
        Get a summary table of all tests
        """
        tbl = TextTable("%name %arch %>duration %result")
        for result in self.results:
            tbl.append(
                {
                    'name': result.case.fullname,
                    'arch': result.case.arch,
                    'duration': f"{result.time:.0f}s",
                    'result': (
                        result.value.upper()
                        if result.value == 'Failure'
                        else result.value
                    )
                }
            )
        return str(tbl)
