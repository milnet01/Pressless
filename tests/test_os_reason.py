"""An error's reason without its path (PRESS-0401)."""
from __future__ import annotations

import ast
import errno
import inspect

from pressless import os_reason


def test_the_reason_never_carries_the_path():
    """A stock file error quotes its path in str(); the reason does not.

    Breaks when `of` answers str(exc), the leak docs/design.md § Logging
    forbids."""
    failed = PermissionError(errno.EACCES, "Permission denied", "/home/someone/site/a.html")
    assert "/home/someone" in str(failed)
    assert os_reason.of(failed) == "Permission denied"


def test_the_type_stands_in_where_there_is_no_reason():
    """An OSError raised without a reason, and any other error, give the
    type's name rather than an empty string or the message.

    Breaks when the fallback is dropped, so a sentence ends in 'None' or
    nothing."""
    assert os_reason.of(FileNotFoundError()) == "FileNotFoundError"
    assert os_reason.of(ValueError("/home/someone/site")) == "ValueError"


def test_it_imports_nothing():
    """A module whose import rule admits it reaches nothing through it.

    Breaks when the helper imports a sibling or anything else, which would
    reach every module that calls it."""
    imported = [node for node in ast.walk(ast.parse(inspect.getsource(os_reason)))
                if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert [ast.unparse(node) for node in imported] == ["from __future__ import annotations"]
