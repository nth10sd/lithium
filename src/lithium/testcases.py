# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium Testcase definitions.

A testcase is a file to be reduced, split in a certain way (eg. bytes, lines).
"""

import abc
import os.path
import re

from .util import LithiumError

DEFAULT = "line"


class Testcase(abc.ABC):
    """Lithium testcase base class."""

    def __init__(self):
        self.before = b""
        self.after = b""
        self.parts = []
        # bool array with same length as `parts`
        # parts with a matchine `False` in `reducible` should
        # not be removed by the Strategy
        self.reducible = []
        self.filename = None
        self.extension = None

    def __len__(self):
        """Length of the testcase in terms of parts to be reduced.

        Returns:
            int: length of parts
        """
        return len(self.parts) - self.reducible.count(False)

    def _slice_xlat(self, start=None, stop=None):
        # translate slice bounds within `[0, len(self))` (excluding non-reducible parts)
        # to bounds within `self.parts`
        len_self = len(self)

        def _clamp(bound, default):
            if bound is None:
                return default
            if bound < 0:
                return max(len_self + bound, 0)
            if bound > len_self:
                return len_self
            return bound

        start = _clamp(start, 0)
        stop = _clamp(stop, len_self)

        opts = [i for i in range(len(self.parts)) if self.reducible[i]]
        opts = [0] + opts[1:] + [len(self.parts)]

        return opts[start], opts[stop]

    def rmslice(self, start, stop):
        """Remove a slice of the testcase between `self.parts[start:stop]`, preserving
        non-reducible parts.

        Slice indices are between 0 and len(self), which may not be = len(self.parts)
        if any parts are marked non-reducible.

        Args:
            start (int): Slice start index
            stop (int): Slice stop index
        """
        start, stop = self._slice_xlat(start, stop)
        keep = [
            x
            for i, x in enumerate(self.parts[start:stop])
            if not self.reducible[start + i]
        ]
        self.parts = self.parts[:start] + keep + self.parts[stop:]
        self.reducible = (
            self.reducible[:start] + ([False] * len(keep)) + self.reducible[stop:]
        )

    def copy(self):
        """Duplicate the current object.

        Returns:
            type(self): A new object with the same type & contents of the original.
        """
        new = type(self)()
        new.before = self.before
        new.after = self.after
        new.parts = self.parts[:]
        new.reducible = self.reducible[:]
        new.filename = self.filename
        new.extension = self.extension
        return new

    def load(self, path):
        """Load and split a testcase from disk.

        Args:
            path (Path or str): Location on disk of testcase to read.

        Raises:
            LithiumError: DDBEGIN/DDEND token mismatch.
        """
        self.__init__()
        self.filename = str(path)
        self.extension = os.path.splitext(self.filename)[1]

        with open(self.filename, "rb") as fileobj:
            before = []
            for line in fileobj:
                before.append(line)
                if line.find(b"DDBEGIN") != -1:
                    self.before = b"".join(before)
                    del before
                    break
                if line.find(b"DDEND") != -1:
                    raise LithiumError(
                        "The testcase (%s) has a line containing 'DDEND' "
                        "without a line containing 'DDBEGIN' before it."
                        % (self.filename,)
                    )
            else:
                # no DDBEGIN/END, `before` contains the whole testcase
                self.split_parts(b"".join(before))
                return

            between = []
            for line in fileobj:
                if line.find(b"DDEND") != -1:
                    self.after = line + fileobj.read()
                    break

                between.append(line)
            else:
                raise LithiumError(
                    "The testcase (%s) has a line containing 'DDBEGIN' "
                    "but no line containing 'DDEND'." % (self.filename,)
                )
            self.split_parts(b"".join(between))

    @staticmethod
    def add_arguments(parser):
        """Add any testcase specific arguments.

        Args:
            parser (ArgumentParser): argparse object to add arguments to.
        """

    def handle_args(self, args):
        """Handle arguments after they have been parsed.

        Args:
            args (argparse.Namespace): parsed argparse arguments.
        """

    @abc.abstractmethod
    def split_parts(self, data):
        """Should take testcase data and update `self.parts`.

        Args:
            data (bytes): Input read from the testcase file
                          (between DDBEGIN/END, if present).
        """

    def dump(self, path=None):
        """Write the testcase to the filesystem.

        Args:
            path (str or Path, optional): Output path (default: self.filename)
        """
        if path is None:
            path = self.filename
        else:
            path = str(path)
        with open(path, "wb") as fileobj:
            fileobj.write(self.before)
            fileobj.writelines(self.parts)
            fileobj.write(self.after)


class TestcaseLine(Testcase):
    """Testcase file split by lines."""

    atom = "line"
    args = ("-l", "--lines")
    arg_help = "Treat the file as a sequence of lines."

    def split_parts(self, data):
        """Take input data and add lines to `parts` to be reduced.

        Args:
            data (bytes): Input data read from the testcase file.
        """
        orig = len(self.parts)
        self.parts.extend(data.splitlines(keepends=True))
        added = len(self.parts) - orig
        self.reducible.extend([True] * added)


class TestcaseChar(Testcase):
    """Testcase file split by bytes."""

    atom = "char"
    args = ("-c", "--char")
    arg_help = "Treat the file as a sequence of bytes."

    def load(self, path):
        super().load(path)
        if (self.before or self.after) and self.parts:
            # Move the line break at the end of the last line out of the reducible
            # part so the "DDEND" line doesn't get combined with another line.
            self.parts.pop()
            self.reducible.pop()
            self.after = b"\n" + self.after

    def split_parts(self, data):
        orig = len(self.parts)
        self.parts.extend(data[i : i + 1] for i in range(len(data)))
        added = len(self.parts) - orig
        self.reducible.extend([True] * added)


class TestcaseJsStr(Testcase):
    """Testcase type for splitting JS strings byte-wise.

    Escapes are also kept together and treated as a single token for reduction.
    ref: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference
        /Global_Objects/String#Escape_notation
    """

    atom = "jsstr char"
    args = ("-j", "--js")
    arg_help = (
        "Same as --char but only operate within JS strings, keeping escapes intact."
    )

    def split_parts(self, data):
        instr = None
        chars = []

        while True:
            last = 0
            while True:
                if instr:
                    match = re.match(
                        br"(\\u[0-9A-Fa-f]{4}|\\x[0-9A-Fa-f]{2}|"
                        br"\\u\{[0-9A-Fa-f]+\}|\\.|.)",
                        data[last:],
                        re.DOTALL,
                    )
                    if not match:
                        break
                    chars.append(len(self.parts))
                    if match.group(0) == instr:
                        instr = None
                        chars.pop()
                else:
                    match = re.search(br"""['"]""", data[last:])
                    if not match:
                        break
                    instr = match.group(0)
                self.parts.append(data[last : last + match.end(0)])
                last += match.end(0)

            if last != len(data):
                self.parts.append(data[last:])

            if instr is None:
                break

            # we hit EOF while looking for end of string, we need to rewind to the state
            # before we matched on that quote character and try again.

            idx = None
            for idx in reversed(range(len(self.parts))):
                if self.parts[idx].endswith(instr) and idx not in chars:
                    break
            else:
                raise RuntimeError("error while backtracking from unmatched " + instr)
            self.parts, data = self.parts[: idx + 1], b"".join(self.parts[idx + 1 :])
            chars = [c for c in chars if c < idx]
            instr = None

        # beginning and end are special because we can put them in
        # self.before/self.after
        if chars:
            # merge everything before first char (pre chars[0]) into self.before
            offset = chars[0]
            if offset:
                header, self.parts = b"".join(self.parts[:offset]), self.parts[offset:]
                self.before = self.before + header
                # update chars which is a list of offsets into self.parts
                chars = [c - offset for c in chars]

            # merge everything after last char (post chars[-1]) into self.after
            offset = chars[-1] + 1
            if offset < len(self.parts):
                self.parts, footer = self.parts[:offset], b"".join(self.parts[offset:])
                self.after = footer + self.after

        # now scan for chars with a gap > 2 between, which means we can merge
        # the goal is to take a string like this:
        #   parts = [a x x x b c]
        #   chars = [0       4 5]
        # and merge it into this:
        #   parts = [a xxx b c]
        #   chars = [0     2 3]
        for i in range(len(chars) - 1):
            char1, char2 = chars[i], chars[i + 1]
            if (char2 - char1) > 2:
                self.parts[char1 + 1 : char2] = [
                    b"".join(self.parts[char1 + 1 : char2])
                ]
                offset = char2 - char1 - 2  # num of parts we eliminated
                chars[i + 1 :] = [c - offset for c in chars[i + 1 :]]

        # default to everything non-reducible
        # mark every char index as reducible, so it can be removed
        self.reducible = [False] * len(self.parts)
        for idx in chars:
            self.reducible[idx] = True


class TestcaseSymbol(Testcase):
    """Testcase type for splitting a file before/after a set of delimiters."""

    atom = "symbol-delimiter"
    DEFAULT_CUT_AFTER = b"?=;{[\n"
    DEFAULT_CUT_BEFORE = b"]}:"
    args = ("-s", "--symbol")
    arg_help = (
        "Treat the file as a sequence of strings separated by tokens. "
        "The characters by which the strings are delimited are defined by "
        "the --cut-before, and --cut-after options."
    )

    def __init__(self):
        super().__init__()
        self._cutter = None
        self.set_cut_chars(self.DEFAULT_CUT_BEFORE, self.DEFAULT_CUT_AFTER)

    def set_cut_chars(self, before, after):
        """Set the bytes used to delimit slice points.

        Args:
            before (bytes): Split file before these delimiters.
            after (bytes): Split file after these delimiters.
        """
        self._cutter = re.compile(
            b"["
            + before
            + b"]?"
            + b"[^"
            + before
            + after
            + b"]*"
            + b"(?:["
            + after
            + b"]|$|(?=["
            + before
            + b"]))"
        )

    def split_parts(self, data):
        for statement in self._cutter.finditer(data):
            if statement.group(0):
                self.parts.append(statement.group(0))
                self.reducible.append(True)

    def handle_args(self, args):
        self.set_cut_chars(args.cut_before, args.cut_after)

    @classmethod
    def add_arguments(cls, parser):
        grp_add = parser.add_argument_group(
            description="Additional options for the symbol-delimiter testcase type."
        )
        grp_add.add_argument(
            "--cut-before",
            default=cls.DEFAULT_CUT_BEFORE,
            help="See --symbol. default: " + cls.DEFAULT_CUT_BEFORE.decode("ascii"),
        )
        grp_add.add_argument(
            "--cut-after",
            default=cls.DEFAULT_CUT_AFTER,
            help="See --symbol. default: " + cls.DEFAULT_CUT_AFTER.decode("ascii"),
        )