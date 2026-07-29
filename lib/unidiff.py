# The MIT License (MIT)
# Copyright (c) 2012 Matias Bordese
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
# OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
# OR OTHER DEALINGS IN THE SOFTWARE.


"""Unified diff parser module."""

import difflib
import re

LINE_TYPE_ADD = "+"
LINE_TYPE_DELETE = "-"
LINE_TYPE_CONTEXT = " "

RE_DIFF_PATCH = re.compile(r"^diff --git (?P<source>[^\t]+) (?P<target>[^\t]+)")

# @@ (source offset, length) (target offset, length) @@ (section header)
RE_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))?\ @@[ ]?(.*)")

# Binary pattern
RE_BINARY_FILE = re.compile(r"^(GIT )?[Bb]inary (files .*differ|patch)$")

# Deleted patterne
RE_DELETED_BINARY_FILE = re.compile(r"^(GIT )?[Bb]inary (files .* /dev/null differ)$")

# renamed pattern
RE_RENAMED_FILE = re.compile(r"^rename from .*$")

#   kept line (context)
# + added line
# - deleted line
# \ No newline case (ignore)
RE_HUNK_BODY_LINE = re.compile(r"^([- \+\\])")


class UnidiffParseException(Exception):
    """Exception when parsing the diff data."""

    pass


class Hunk(object):
    """Each of the modified blocks of a file."""

    def __init__(
        self, src_start=0, src_len=0, tgt_start=0, tgt_len=0, section_header=""
    ):
        if src_len is None:
            src_len = 1
        if tgt_len is None:
            tgt_len = 1
        self.source_start = int(src_start)
        self.source_length = int(src_len)
        self.target_start = int(tgt_start)
        self.target_length = int(tgt_len)
        self.section_header = section_header
        self.source_lines = []
        self.target_lines = []
        self.source_types = []
        self.target_types = []
        self.modified = 0
        self.added = 0
        self.deleted = 0
        self._unidiff_generator = None

    def __repr__(self):
        return "<@@ %d,%d %d,%d @@ %s>" % (
            self.source_start,
            self.source_length,
            self.target_start,
            self.target_length,
            self.section_header,
        )

    def as_unified_diff(self):
        """Output hunk data in unified diff format."""
        if self._unidiff_generator is None:
            self._unidiff_generator = difflib.unified_diff(
                self.source_lines, self.target_lines
            )
            # throw the header information
            for i in range(3):
                next(self._unidiff_generator)

        head = "@@ -%d,%d +%d,%d @@\n" % (
            self.source_start,
            self.source_length,
            self.target_start,
            self.target_length,
        )
        yield head
        while True:
            yield next(self._unidiff_generator)

    def is_valid(self):
        """Check hunk header data matches entered lines info."""
        return (
            len(self.source_lines) == self.source_length
            and len(self.target_lines) == self.target_length
        )

    def append_context_line(self, line):
        """Add a new context line to the hunk."""
        self.source_lines.append(line)
        self.target_lines.append(line)
        self.source_types.append(LINE_TYPE_CONTEXT)
        self.target_types.append(LINE_TYPE_CONTEXT)

    def append_added_line(self, line):
        """Add a new added line to the hunk."""
        self.target_lines.append(line)
        self.target_types.append(LINE_TYPE_ADD)
        self.added += 1

    def append_deleted_line(self, line):
        """Add a new deleted line to the hunk."""
        self.source_lines.append(line)
        self.source_types.append(LINE_TYPE_DELETE)
        self.deleted += 1

    def add_to_modified_counter(self, mods):
        """Update the number of lines modified in the hunk."""
        self.deleted -= mods
        self.added -= mods
        self.modified += mods


class PatchedFile(list):
    """Data of a patched file, each element is a Hunk."""

    def __init__(self, source="", target=""):
        super(PatchedFile, self).__init__()
        self.source_file = source
        self.target_file = target
        self.binary = False
        self.renamed = False
        self._deleted = False

    def __repr__(self):
        return "%s: %s" % (self.target_file, super(PatchedFile, self).__repr__())

    def __str__(self):
        s = self.path + "\n"
        for e in enumerate([repr(e) for e in self]):
            s += "Hunk #%s: %s\n" % e
        s += "\n"
        return s

    def as_unified_diff(self):
        """Output file changes in unified diff format."""
        source = "--- %s\n" % self.source_file
        yield source

        target = "+++ %s\n" % self.target_file
        yield target

        for hunk in self:
            hunk_data = hunk.as_unified_diff()
            for line in hunk_data:
                yield line

    @property
    def path(self):
        """Return the file path abstracted from VCS."""
        # TODO: improve git/hg detection
        if self.renamed:
            filepath = self.target_file
        elif self.source_file == "/dev/null":
            filepath = self.target_file
        else:
            filepath = self.source_file
        if filepath.startswith("a/") or filepath.startswith("b/"):
            filepath = filepath[2:]
        return filepath.strip()

    @property
    def added(self):
        """Return the file total added lines."""
        return sum([hunk.added for hunk in self])

    @property
    def deleted(self):
        """Return the file total deleted lines."""
        return sum([hunk.deleted for hunk in self])

    @property
    def modified(self):
        """Return the file total modified lines."""
        return sum([hunk.modified for hunk in self])

    @property
    def is_added_file(self):
        """Return True if this patch adds a file."""
        return (
            len(self) == 1 and self[0].source_start == 0 and self[0].source_length == 0
        )

    @property
    def is_deleted_file(self):
        """Return True if this patch deletes a file."""
        return self._deleted or (
            len(self) == 1 and self[0].target_start == 0 and self[0].target_length == 0
        )

    @property
    def is_modified_file(self):
        """Return True if this patch modifies a file."""
        return not (self.is_added_file or self.is_deleted_file)


class PatchSet(list):
    """A list of PatchedFiles."""

    def as_unified_diff(self):
        """Output patch data in unified diff format.

        It won't necessarily match the original unified diff,
        but it should be equivalent.
        """
        for patched_file in self:
            data = patched_file.as_unified_diff()
            for line in data:
                yield line

    def __str__(self):
        return "".join([str(e) for e in self])


def _parse_hunk(
    diff, source_start, source_len, target_start, target_len, section_header
):
    """Parse a diff hunk details."""
    hunk = Hunk(source_start, source_len, target_start, target_len, section_header)
    modified = 0
    deleting = 0
    for line in diff:
        valid_line = RE_HUNK_BODY_LINE.match(line)
        if not valid_line:
            raise UnidiffParseException("Hunk diff data expected")

        action = valid_line.group(0)
        original_line = line[1:]
        if action == LINE_TYPE_ADD:
            hunk.append_added_line(original_line)
            # modified lines == deleted immediately followed by added
            if deleting > 0:
                modified += 1
                deleting -= 1
        elif action == LINE_TYPE_DELETE:
            hunk.append_deleted_line(original_line)
            deleting += 1
        elif action == LINE_TYPE_CONTEXT:
            hunk.append_context_line(original_line)
            hunk.add_to_modified_counter(modified)
            # reset modified auxiliar variables
            deleting = 0
            modified = 0

        # check hunk len(old_lines) and len(new_lines) are ok
        if hunk.is_valid():
            break

    return hunk


def parse_unidiff(diff):
    """Unified diff parser, takes a file-like object as argument."""
    ret = PatchSet()
    current_patch = None
    source_file = None
    target_file = None

    for line in diff:
        ## check for source file header
        check_source = RE_DIFF_PATCH.match(line)
        if check_source:
            source_file = check_source.group("source")
            target_file = check_source.group("target")
            current_patch = PatchedFile(source_file, target_file)
            ret.append(current_patch)
            continue

        # check for binary format
        if RE_BINARY_FILE.match(line):
            current_patch.binary = True

        if RE_DELETED_BINARY_FILE.match(line):
            current_patch._deleted = True

        # check for renamed file
        if RE_RENAMED_FILE.match(line):
            current_patch.renamed = True

        # check for hunk header
        re_hunk_header = RE_HUNK_HEADER.match(line)
        if re_hunk_header:
            hunk_info = re_hunk_header.groups()
            hunk = _parse_hunk(diff, *hunk_info)
            current_patch.append(hunk)
    return ret
