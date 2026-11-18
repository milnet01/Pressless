"""The tray's shared half: its three actions, on the Face served last
(PRESS-0204 INV-3), and a tray that cannot start (INV-6).

The system half is conftest's QuietIcon, or one that fails; a fake Face
records what the actions did to it.
"""
from __future__ import annotations

import pytest
from conftest import QuietIcon

from pressless import tray


class _Face:
    """As much of face.Face as the tray touches."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.links: list[str] = []
        self.notes: list[str] = []
        self._at_stop = []

    def fresh_link(self, path: str = "/") -> str:
        self.links.append(f"http://{self.name}{path}?t={len(self.links)}")
        return self.links[-1]

    def note(self, text: str) -> None:
        self.notes.append(text)

    def at_stop(self, action) -> None:
        self._at_stop.append(action)

    def stop(self) -> None:
        for action in self._at_stop:
            action()


@pytest.fixture
def opened(monkeypatch) -> list[str]:
    links: list[str] = []
    monkeypatch.setattr(tray.webbrowser, "open", lambda link: links.append(link) or True)
    return links


def test_each_entry_acts_on_the_face_served_last(opened) -> None:
    """INV-3: Open opens that Face's fresh link, Restart calls its restart,
    Stop calls stop once however often it is chosen; once the Face stops,
    Open and Restart do nothing, and Stop still stops.

    Breaks when the tray keeps the first Face it was given, so Open after a
    restart opens a dead port."""
    stops, restarts = [], []
    icon = tray.Tray(lambda: stops.append(1))
    first, second = _Face("first"), _Face("second")
    icon.serve(first, lambda: restarts.append("first"))
    icon.serve(second, lambda: restarts.append("second"))
    first.stop()        # late: it must not take the second Face with it

    icon.run(tray.OPEN)
    icon.run(tray.RESTART)
    assert opened == second.links and len(opened) == 1 and first.links == []
    assert restarts == ["second"]
    assert [entry for entry, _ in QuietIcon.made[0].entries] == [
        tray.OPEN, tray.RESTART, tray.STOP]
    assert len(QuietIcon.made) == 1, "a second serve started a second icon"

    second.stop()
    icon.run(tray.OPEN)
    icon.run(tray.RESTART)
    assert len(opened) == 1 and restarts == ["second"], "an entry acted on a stopped Face"

    icon.run(tray.STOP)
    icon.run(tray.STOP)
    assert stops == [1]
    icon.close()
    icon.close()
    assert QuietIcon.made[0].closed


def test_an_action_that_raises_is_noted_not_raised(monkeypatch, capsys) -> None:
    """INV-3's last clause: a failure is noted by type in the log of the Face
    served last, and the icon stays. Where no browser opens, the link is
    printed, as at launch. Once the Face stops, a failure is not noted."""
    def no_browser(link):
        raise RuntimeError("no browser")

    def broken():
        raise ValueError("broken")

    monkeypatch.setattr(tray.webbrowser, "open", no_browser)
    served = _Face("served")
    icon = tray.Tray(broken)
    icon.serve(served, broken)

    icon.run(tray.OPEN)
    assert served.links[0] in capsys.readouterr().out
    icon.run(tray.RESTART)
    assert served.notes == ["a tray action failed: ValueError"]

    served.stop()
    icon.run(tray.STOP)
    assert served.notes == ["a tray action failed: ValueError"]
    assert not QuietIcon.made[0].closed


class _NoTray(QuietIcon):
    def start(self) -> None:
        raise OSError("no session bus")


def test_a_tray_that_cannot_start_changes_nothing(monkeypatch, opened) -> None:
    """INV-6: start() is False, the Face's log says why, and nothing raises."""
    monkeypatch.setattr(tray, "_Icon", _NoTray)
    served = _Face("served")
    icon = tray.Tray(lambda: None)
    icon.serve(served, lambda: None)
    assert served.notes == ["the tray icon could not start: OSError"]
    assert icon.start() is False
    icon.close()
