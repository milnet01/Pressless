"""One shared durability watcher for the four atomic writers (PRESS-0039).

Settings, Credentials, the Store and the Insights cache each write a temporary
and rename it over the target. rename(2) orders the namespace, not the data, so
the rename can reach the disk before the blocks and leave an empty file where
three specs promise the previous one. The fix is an fsync of the temporary's
descriptor before the rename, and the ORDER is the whole of it: the file is
byte-identical either way until the power fails, so nothing read back off the
disk can tell a synced write from an unsynced one.

Shared rather than copied for the reason _open_watch.py gives -- two copies of
a watcher are two watchers that will disagree.
"""
from __future__ import annotations

import os
import tempfile


def _watch_durability(monkeypatch) -> list[tuple]:
    """Record mkstemp, fsync and replace in the order the code performs them.

    tempfile.mkstemp is watched rather than os.open because it is what hands
    the writer its descriptor, and the descriptor is what the fsync has to
    name: syncing any other one leaves the temporary's blocks in the cache.
    """
    events: list[tuple] = []
    real_mkstemp = tempfile.mkstemp
    real_fsync = os.fsync
    real_replace = os.replace

    def watched_mkstemp(*args, **kwargs):
        handle, path = real_mkstemp(*args, **kwargs)
        events.append(("mkstemp", handle))
        return handle, path

    def watched_fsync(descriptor):
        # The size AT the sync, not afterwards: an fsync that is not
        # preceded by a flush syncs an empty file and the buffer reaches
        # the kernel later, at close, after the sync that was meant to
        # make it durable. Nothing on disk afterwards shows that.
        events.append(("fsync", descriptor, os.fstat(descriptor).st_size))
        return real_fsync(descriptor)

    def watched_replace(source, destination, *args, **kwargs):
        events.append(("replace", os.fspath(destination)))
        return real_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", watched_mkstemp)
    monkeypatch.setattr(os, "fsync", watched_fsync)
    monkeypatch.setattr(os, "replace", watched_replace)
    return events


def _assert_synced_before_replace(events, what: str) -> None:
    """Every rename was preceded by an fsync of the descriptor it renames.

    Only the fsyncs recorded after that rename's own mkstemp count. Descriptor
    numbers are reused, so a writer that synced an earlier temporary and not
    this one would otherwise pass on the recycled number.
    """
    renames = [index for index, event in enumerate(events) if event[0] == "replace"]
    assert renames, (
        f"{what} never reached os.replace, so there is no rename whose "
        f"durability this could assert"
    )
    for index in renames:
        target = events[index][1]
        opened = [i for i in range(index) if events[i][0] == "mkstemp"]
        assert opened, (
            f"{what} renamed onto {target} with no mkstemp temporary before "
            f"it, so the watch cannot name the descriptor that owes an fsync"
        )
        start = opened[-1]
        handle = events[start][1]
        synced = [events[i] for i in range(start, index) if events[i][0] == "fsync"]
        sizes = [size for _, descriptor, size in synced if descriptor == handle]
        assert sizes, (
            f"{what} renamed onto {target} without os.fsync on the "
            f"temporary's descriptor first. rename(2) orders the namespace, "
            f"not the data, so a power loss can commit the rename before the "
            f"blocks and leave an empty file where the previous one was"
        )
        assert max(sizes) > 0, (
            f"{what} synced the temporary for {target} while it was still "
            f"empty, so what it made durable was nothing: the write is "
            f"buffered in the process and needs a flush before the fsync"
        )
