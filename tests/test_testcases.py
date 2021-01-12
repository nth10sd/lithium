# coding=utf-8
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Lithium Testcase* tests"""

from pathlib import Path

import pytest

import lithium

pytestmark = pytest.mark.usefixtures("tmp_cwd")  # pylint: disable=invalid-name


def test_line():
    """Test simple line splitting"""
    test = lithium.testcases.TestcaseLine()
    test_path = Path("a.txt")
    test_path.write_bytes(b"hello")
    test.load(test_path)
    test_path.unlink()
    test.dump()
    assert test_path.read_bytes() == b"hello"
    assert test.filename == "a.txt"
    assert test.extension == ".txt"
    assert test.before == b""
    assert test.parts == [b"hello"]
    assert test.after == b""
    assert test.reducible == [True]
    assert len(test) == 1
    test.dump("b.txt")
    assert Path("b.txt").read_bytes() == b"hello"


def test_line_dd():
    """Test line splitting with DDBEGIN/END"""
    test = lithium.testcases.TestcaseLine()
    test_path = Path("a.txt")
    test_path.write_bytes(b"pre\n" b"DDBEGIN\n" b"data\n" b"2\n" b"DDEND\n" b"post\n")
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\n"
    assert test.parts == [b"data\n", b"2\n"]
    assert test.reducible == [True, True]
    assert test.after == b"DDEND\npost\n"
    assert len(test) == 2


def test_char_dd():
    """Test char splitting with DDBEGIN/END"""
    test = lithium.testcases.TestcaseChar()
    test_path = Path("a.txt")
    test_path.write_bytes(b"pre\n" b"DDBEGIN\n" b"data\n" b"2\n" b"DDEND\n" b"post\n")
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\n"
    assert test.parts == [b"d", b"a", b"t", b"a", b"\n", b"2"]
    assert test.reducible == [True] * 6
    assert len(test) == 6
    assert test.after == b"\nDDEND\npost\n"


def test_jsstr_0():
    """Test that the TestcaseJsStr class splits JS strings properly 0"""
    test = lithium.testcases.TestcaseJsStr()
    test_path = Path("a.txt")
    test_path.write_bytes(
        b"pre\n"
        b"DDBEGIN\n"
        b"data\n"
        b"2\n"
        b"'\\u{123}\"1\\x32\\023\n'\n"  # a str with some escapes
        b'""\n'  # empty string
        b'"\\u12345Xyz"\n'  # another str with the last escape format
        b"Data\xFF\n"
        b'"x\xFF" something\n'  # last str
        b"DDEND\n"
        b"post\n"
    )
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\ndata\n2\n'"
    assert test.parts == [
        b"\\u{123}",
        b'"',
        b"1",
        b"\\x32",
        b"\\0",
        b"2",
        b"3",
        b"\n",  # first JS str
        b'\'\n""\n"',  # empty string contains no chars, included with in-between data
        b"\\u1234",
        b"5",
        b"X",
        b"y",
        b"z",  # next JS str
        b'"\nData\xFF\n"',
        b"x",
        b"\xFF",
    ]  # last JS str
    assert test.after == b'" something\nDDEND\npost\n'
    assert test.reducible == [True] * 8 + [False] + [True] * 5 + [False] + [True] * 2
    assert len(test) == 15


def test_jsstr_1():
    """Test that the TestcaseJsStr class splits JS strings properly 1"""
    test = lithium.testcases.TestcaseJsStr()
    test_path = Path("a.txt")
    test_path.write_bytes(b"'xabcx'")
    test.load(test_path)
    assert test.before == b"'"
    assert test.parts == [b"x", b"a", b"b", b"c", b"x"]
    assert len(test) == 5
    assert test.reducible == [True] * 5
    assert test.after == b"'"


def test_jsstr_2():
    """Test that the TestcaseJsStr class splits JS strings properly 2"""
    test = lithium.testcases.TestcaseJsStr()
    test_path = Path("a.txt")
    test_path.write_bytes(b"'x'abcx'")
    test.load(test_path)
    assert test.before == b"'"
    assert test.parts == [b"x"]
    assert len(test) == 1
    assert test.reducible == [True]
    assert test.after == b"'abcx'"


def test_jsstr_3():
    """Test that the TestcaseJsStr class splits JS strings properly 3"""
    test = lithium.testcases.TestcaseJsStr()
    test_path = Path("a.txt")
    test_path.write_bytes(b'\'x"abc"x')
    test.load(test_path)
    assert test.before == b"'x\""
    assert test.parts == [b"a", b"b", b"c"]
    assert len(test) == 3
    assert test.reducible == [True] * 3
    assert test.after == b'"x'


def test_symbol_0():
    """Test symbol splitting 0"""
    test = lithium.testcases.TestcaseSymbol()
    test_path = Path("a.txt")
    test_path.write_bytes(b"pre\n" b"DDBEGIN\n" b"d{a}ta\n" b"2\n" b"DDEND\n" b"post\n")
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\n"
    assert test.parts == [b"d{", b"a", b"}ta\n", b"2\n"]
    assert len(test) == 4
    assert test.reducible == [True] * 4
    assert test.after == b"DDEND\npost\n"


def test_symbol_1():
    """Test symbol splitting 1"""
    test = lithium.testcases.TestcaseSymbol()
    test_path = Path("a.txt")
    test_path.write_bytes(
        b"pre\n" b"DDBEGIN\n" b"{data\n" b"2}\n}" b"DDEND\n" b"post\n"
    )
    test.load(test_path)
    assert test.before == b"pre\nDDBEGIN\n"
    assert test.parts == [b"{", b"data\n", b"2", b"}\n"]
    assert test.after == b"}DDEND\npost\n"
    assert len(test) == 4
    assert test.reducible == [True] * 4


@pytest.mark.parametrize(
    "data,error",
    [
        (b"DDEND\n", "'DDEND' without"),
        (b"DDBEGIN DDEND\n", "'DDBEGIN' but no"),
        (b"DDBEGIN DDEND\n", "'DDBEGIN' but no"),
        (b"DDEND DDBEGIN\n", "'DDBEGIN' but no"),
        (b"DDBEGIN\n", "'DDBEGIN' but no"),
    ],
)
def test_errors(data, error):
    """Test DDBEGIN/END errors"""
    test = lithium.testcases.TestcaseLine()
    test_path = Path("a.txt")
    test_path.write_bytes(data)
    with pytest.raises(
        lithium.LithiumError,
        match=r"^The testcase \(%s\) has a line containing %s" % (test_path, error),
    ):
        test.load(test_path)


def test_reducible_slices():
    """Test reducible part slicing"""
    # pylint: disable=protected-access
    test = lithium.testcases.TestcaseChar()
    test.split_parts(b"0123456789")
    assert len(test.parts) == len(test.reducible)
    assert all(test.reducible)
    assert test.parts == [b"0", b"1", b"2", b"3", b"4", b"5", b"6", b"7", b"8", b"9"]
    assert test.after == test.before == b""
    # odd elements are fixed
    test.reducible = [False, True] * 5
    assert len(test.parts) == len(test.reducible)
    assert len(test) == 5
    assert test.parts[slice(*test._slice_xlat(0, 0))] == []
    assert test.parts[slice(*test._slice_xlat(0, 1))] == [b"0", b"1", b"2"]
    assert test.parts[slice(*test._slice_xlat(1, 2))] == [b"3", b"4"]
    assert test.parts[slice(*test._slice_xlat(2, 3))] == [b"5", b"6"]
    assert test.parts[slice(*test._slice_xlat(3, 4))] == [b"7", b"8"]
    assert test.parts[slice(*test._slice_xlat(4, 5))] == [b"9"]
    assert test.parts[slice(*test._slice_xlat(5, 6))] == []
    assert test.parts[slice(*test._slice_xlat(-1))] == [b"9"]
    assert test.parts[slice(*test._slice_xlat(-2, -1))] == [b"7", b"8"]
    assert test.parts[slice(*test._slice_xlat(0, 2))] == [b"0", b"1", b"2", b"3", b"4"]
    assert test.parts[slice(*test._slice_xlat(3))] == [b"7", b"8", b"9"]
    # even elements are fixed
    test.reducible = [True, False] * 5
    assert len(test.parts) == len(test.reducible)
    assert len(test) == 5
    assert test.parts[slice(*test._slice_xlat(0, 0))] == []
    assert test.parts[slice(*test._slice_xlat(0, 1))] == [b"0", b"1"]
    assert test.parts[slice(*test._slice_xlat(1, 2))] == [b"2", b"3"]
    assert test.parts[slice(*test._slice_xlat(2, 3))] == [b"4", b"5"]
    assert test.parts[slice(*test._slice_xlat(3, 4))] == [b"6", b"7"]
    assert test.parts[slice(*test._slice_xlat(4, 5))] == [b"8", b"9"]
    assert test.parts[slice(*test._slice_xlat(5, 6))] == []
    assert test.parts[slice(*test._slice_xlat(0, 2))] == [b"0", b"1", b"2", b"3"]
    assert test.parts[slice(*test._slice_xlat(3))] == [b"6", b"7", b"8", b"9"]
    # 2 fixed between every reducible (first reducible = 0)
    test.reducible = [True, False, False] * 3 + [True]
    assert len(test.parts) == len(test.reducible)
    assert len(test) == 4
    assert test.parts[slice(*test._slice_xlat(0, 0))] == []
    assert test.parts[slice(*test._slice_xlat(0, 1))] == [b"0", b"1", b"2"]
    assert test.parts[slice(*test._slice_xlat(1, 2))] == [b"3", b"4", b"5"]
    assert test.parts[slice(*test._slice_xlat(2, 3))] == [b"6", b"7", b"8"]
    assert test.parts[slice(*test._slice_xlat(3, 4))] == [b"9"]
    assert test.parts[slice(*test._slice_xlat(4, 5))] == []
    assert test.parts[slice(*test._slice_xlat(0, 2))] == [
        b"0",
        b"1",
        b"2",
        b"3",
        b"4",
        b"5",
    ]
    assert test.parts[slice(*test._slice_xlat(3))] == [b"9"]
    # 2 fixed between every reducible (first reducible = 1)
    test.reducible = [False, True, False] * 3 + [False]
    assert len(test.parts) == len(test.reducible)
    assert len(test) == 3
    assert test.parts[slice(*test._slice_xlat(0, 0))] == []
    assert test.parts[slice(*test._slice_xlat(0, 1))] == [b"0", b"1", b"2", b"3"]
    assert test.parts[slice(*test._slice_xlat(1, 2))] == [b"4", b"5", b"6"]
    assert test.parts[slice(*test._slice_xlat(2, 3))] == [b"7", b"8", b"9"]
    assert test.parts[slice(*test._slice_xlat(3, 4))] == []
    assert test.parts[slice(*test._slice_xlat(0, 2))] == [
        b"0",
        b"1",
        b"2",
        b"3",
        b"4",
        b"5",
        b"6",
    ]
    assert test.parts[slice(*test._slice_xlat(1))] == [
        b"4",
        b"5",
        b"6",
        b"7",
        b"8",
        b"9",
    ]
    # 2 fixed between every reducible (first reducible = 2)
    test.reducible = [False, False, True] * 3 + [False]
    assert len(test.parts) == len(test.reducible)
    assert len(test) == 3
    assert test.parts[slice(*test._slice_xlat(0, 0))] == []
    assert test.parts[slice(*test._slice_xlat(0, 1))] == [b"0", b"1", b"2", b"3", b"4"]
    assert test.parts[slice(*test._slice_xlat(1, 2))] == [b"5", b"6", b"7"]
    assert test.parts[slice(*test._slice_xlat(2, 3))] == [b"8", b"9"]
    assert test.parts[slice(*test._slice_xlat(3, 4))] == []
    assert test.parts[slice(*test._slice_xlat(0, 2))] == [
        b"0",
        b"1",
        b"2",
        b"3",
        b"4",
        b"5",
        b"6",
        b"7",
    ]
    assert test.parts[slice(*test._slice_xlat(1))] == [b"5", b"6", b"7", b"8", b"9"]
    # 2 reducible between every fixed (first fixed = 0)
    test.reducible = [False, True, True] * 3 + [False]
    assert len(test.parts) == len(test.reducible)
    assert len(test) == 6
    assert test.parts[slice(*test._slice_xlat(0, 0))] == []
    assert test.parts[slice(*test._slice_xlat(0, 1))] == [b"0", b"1"]
    assert test.parts[slice(*test._slice_xlat(1, 2))] == [b"2", b"3"]
    assert test.parts[slice(*test._slice_xlat(2, 3))] == [b"4"]
    assert test.parts[slice(*test._slice_xlat(3, 4))] == [b"5", b"6"]
    assert test.parts[slice(*test._slice_xlat(4, 5))] == [b"7"]
    assert test.parts[slice(*test._slice_xlat(5, 6))] == [b"8", b"9"]
    assert test.parts[slice(*test._slice_xlat(6, 7))] == []
    assert test.parts[slice(*test._slice_xlat(0, 2))] == [b"0", b"1", b"2", b"3"]
    assert test.parts[slice(*test._slice_xlat(3))] == [b"5", b"6", b"7", b"8", b"9"]
    # 2 reducible between every fixed (first fixed = 1)
    test.reducible = [True, False, True] * 3 + [True]
    assert len(test.parts) == len(test.reducible)
    assert len(test) == 7
    assert test.parts[slice(*test._slice_xlat(0, 0))] == []
    assert test.parts[slice(*test._slice_xlat(0, 1))] == [b"0", b"1"]
    assert test.parts[slice(*test._slice_xlat(1, 2))] == [b"2"]
    assert test.parts[slice(*test._slice_xlat(2, 3))] == [b"3", b"4"]
    assert test.parts[slice(*test._slice_xlat(3, 4))] == [b"5"]
    assert test.parts[slice(*test._slice_xlat(4, 5))] == [b"6", b"7"]
    assert test.parts[slice(*test._slice_xlat(5, 6))] == [b"8"]
    assert test.parts[slice(*test._slice_xlat(6, 7))] == [b"9"]
    assert test.parts[slice(*test._slice_xlat(7, 8))] == []
    assert test.parts[slice(*test._slice_xlat(0, 2))] == [b"0", b"1", b"2"]
    assert test.parts[slice(*test._slice_xlat(3))] == [b"5", b"6", b"7", b"8", b"9"]
    # 2 reducible between every fixed (first fixed = 2)
    test.reducible = [True, True, False] * 3 + [True]
    assert len(test.parts) == len(test.reducible)
    assert len(test) == 7
    assert test.parts[slice(*test._slice_xlat(0, 0))] == []
    assert test.parts[slice(*test._slice_xlat(0, 1))] == [b"0"]
    assert test.parts[slice(*test._slice_xlat(1, 2))] == [b"1", b"2"]
    assert test.parts[slice(*test._slice_xlat(2, 3))] == [b"3"]
    assert test.parts[slice(*test._slice_xlat(3, 4))] == [b"4", b"5"]
    assert test.parts[slice(*test._slice_xlat(4, 5))] == [b"6"]
    assert test.parts[slice(*test._slice_xlat(5, 6))] == [b"7", b"8"]
    assert test.parts[slice(*test._slice_xlat(6, 7))] == [b"9"]
    assert test.parts[slice(*test._slice_xlat(7, 8))] == []
    assert test.parts[slice(*test._slice_xlat(0, 2))] == [b"0", b"1", b"2"]
    assert test.parts[slice(*test._slice_xlat(3))] == [
        b"4",
        b"5",
        b"6",
        b"7",
        b"8",
        b"9",
    ]