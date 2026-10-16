"""PRESS-0278: an About page saying which Pressless this is, and that it is
an independent project, linked from every screen's top bar."""
from __future__ import annotations

from pathlib import Path

from test_face import _Client

from pressless import __version__, about, face


def test_the_about_page_names_the_version_and_who_is_not_behind_it(tmp_path: Path) -> None:
    """Breaks when the page drops the version, or any of the three names
    the disclaimer says Pressless is independent of."""
    served = face.serve(tmp_path)
    try:
        about.register(served)
        status, _, body = _Client(served).request("GET", about.ADDRESS)
    finally:
        served.stop()
    assert status == 200
    assert f"Pressless {__version__}" in body
    for name in ("GitHub", "Google", "WordPress"):
        assert name in body.split("independent project", 1)[1], name
    assert "https://github.com/milnet01/Pressless" in body


def test_every_page_links_to_the_about_page(tmp_path: Path) -> None:
    """Breaks when the top bar loses the link, on an ordinary page or on a
    failure page."""
    def broken(request: face.Request) -> str:
        raise ValueError("x")

    served = face.serve(tmp_path)
    try:
        served.add_page("GET", "/words", lambda request: "<p>Words</p>")
        served.add_page("GET", "/broken", broken)
        client = _Client(served)
        for path in ("/words", "/broken"):
            _, _, body = client.request("GET", path)
            bar = body.split('<header class="bar">', 1)[1].split("</header>", 1)[0]
            assert '<a href="/about">About</a>' in bar, path
    finally:
        served.stop()
