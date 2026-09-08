"""The durability watch catches an unsynced rename (PRESS-0110).

`tests/_durability_watch.py` is shared by four writers' tests, and it is the
only thing standing between PRESS-0039 and a silent regression. So it needs
its own test: a watcher that cannot fail makes all four of them green for the
wrong reason, and nothing downstream would say so.

The case that mattered is a writer that opens TWO temporaries before renaming
either. The watch used to pair each rename with the LAST mkstemp before it, so
one fsync satisfied both renames and the unsynced file passed -- PRESS-0039's
exact failure, inside the test written to catch it. Pairing is by path now,
and these tests are what hold it there.

Written against the watch directly rather than against a writer, because no
writer in `src/` opens two temporaries today: the defect is reachable only by
a writer that does not exist yet, which is precisely why a real writer's suite
cannot cover it.
"""
from __future__ import annotations

import os
import tempfile

import pytest
from _durability_watch import _assert_synced_before_replace, _watch_durability


def _write_and_close(handle, payload: bytes = b"durable") -> None:
    """Put bytes on the descriptor and flush them to the kernel.

    Written through the descriptor itself, so the fsync the watch records has
    something to make durable -- the watch asserts a non-zero size at the sync.
    """
    os.write(handle, payload)


def test_two_temporaries_one_fsync_is_caught(monkeypatch, tmp_path):
    """The regression. A writer opens two temporaries, syncs only the second,
    and renames both. The first rename is undurable and must be reported.

    Breaks when the watch goes back to pairing a rename with whichever mkstemp
    came last, which is what let one fsync answer for two files."""
    events = _watch_durability(monkeypatch)

    first_handle, first_path = tempfile.mkstemp(dir=str(tmp_path))
    second_handle, second_path = tempfile.mkstemp(dir=str(tmp_path))
    _write_and_close(first_handle)
    _write_and_close(second_handle)

    os.fsync(second_handle)  # only the second is made durable
    os.close(first_handle)
    os.close(second_handle)

    os.replace(first_path, str(tmp_path / "first"))
    os.replace(second_path, str(tmp_path / "second"))

    with pytest.raises(AssertionError) as caught:
        _assert_synced_before_replace(events, "the two-temporary writer")
    assert "without os.fsync" in str(caught.value), (
        f"the watch failed for some reason other than the missing fsync: "
        f"{caught.value}"
    )


def test_two_temporaries_both_synced_passes(monkeypatch, tmp_path):
    """The same writer, done correctly, is not reported. Without this the
    fix above could be a watch that fails on everything."""
    events = _watch_durability(monkeypatch)

    first_handle, first_path = tempfile.mkstemp(dir=str(tmp_path))
    second_handle, second_path = tempfile.mkstemp(dir=str(tmp_path))
    _write_and_close(first_handle)
    _write_and_close(second_handle)

    os.fsync(first_handle)
    os.fsync(second_handle)
    os.close(first_handle)
    os.close(second_handle)

    os.replace(first_path, str(tmp_path / "first"))
    os.replace(second_path, str(tmp_path / "second"))

    _assert_synced_before_replace(events, "the correct two-temporary writer")


def test_an_unrenamed_temporary_does_not_displace_the_pairing(monkeypatch, tmp_path):
    """A probe that opens a temporary and never renames it is harmless.

    `tests/_mode_support.py` does exactly this, and it is patched by this same
    watch. Under positional pairing its throwaway became the temporary the
    next rename was checked against, so a correct writer failed. Breaks when
    pairing stops keying on the path os.replace was handed."""
    events = _watch_durability(monkeypatch)

    handle, path = tempfile.mkstemp(dir=str(tmp_path))
    _write_and_close(handle)
    os.fsync(handle)
    os.close(handle)

    probe_handle, probe_path = tempfile.mkstemp(dir=str(tmp_path), prefix=".modeprobe-")
    os.close(probe_handle)
    os.unlink(probe_path)

    os.replace(path, str(tmp_path / "target"))

    _assert_synced_before_replace(events, "a correct writer beside a mode probe")


def test_an_fsync_of_an_empty_temporary_is_caught(monkeypatch, tmp_path):
    """The watch's other clause: a sync that made nothing durable.

    An fsync issued before the writer's buffer is flushed syncs an empty file,
    and the bytes reach the kernel later at close -- after the sync meant to
    make them durable. Nothing on disk afterwards shows that, which is why the
    watch records the size AT the sync.

    Found by mutation probe while fixing PRESS-0110: relaxing the size check to
    `>= 0` left the whole suite green, so the clause could not fail and was
    evidence of nothing. Breaks when the size stops being read at the sync."""
    events = _watch_durability(monkeypatch)

    handle, path = tempfile.mkstemp(dir=str(tmp_path))
    os.fsync(handle)  # nothing written yet: this makes an empty file durable
    _write_and_close(handle)
    os.close(handle)

    os.replace(path, str(tmp_path / "target"))

    with pytest.raises(AssertionError) as caught:
        _assert_synced_before_replace(events, "the flush-after-sync writer")
    assert "still empty" in str(caught.value), (
        f"the watch failed for some reason other than the empty sync: "
        f"{caught.value}"
    )
