"""PRESS-0195 § 4.2: the menu is the user's own HTML, and these edit one page's
link in it (docs/specs/PRESS-0195-add-remove-rename-pages.md, INV-5 to INV-7).

The fixtures are the starter's menu, a one-line menu and a four-link menu laid
out as the first writer's live site is, with its Journal link last.
"""

from __future__ import annotations

import pytest

from pressless import menu, starter

ONE_LINE = ('<nav><a href="{{UP}}index.html" data-nav="Home">Home</a> '
            '<a href="{{UP}}pages/about.html" data-nav="About">About</a></nav>')
FOUR = ('    <nav class="primary" aria-label="Primary">\n'
        '      <a href="{{UP}}index.html" data-nav="Home">Home</a>\n'
        '      <a href="{{UP}}pages/about.html" data-nav="About">About</a>\n'
        '      <a href="{{UP}}pages/music.html" data-nav="Music">Music</a>\n'
        '      <a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a>\n'
        '    </nav>')
LISTED = ('<nav><ul>\n'
          '  <li><a href="{{UP}}index.html">Home</a></li>\n'
          '  <li><a href="{{UP}}pages/about.html">About</a></li>\n'
          '</ul></nav>')


def _menus():
    return {"starter": starter._navigation(), "one line": ONE_LINE, "four": FOUR}


@pytest.mark.parametrize("kind", ["starter", "one line", "four"])
def test_add_places_the_link_after_the_last_page(kind):
    """INV-5: one link to the new page, after the last pages/ link and with
    that link's leading whitespace; every other byte kept.

    Breaks when the link goes after Journal, or the separator is hard-coded."""
    text = _menus()[kind]
    added = menu.add(text, "gigs", "Gigs & Tours")
    link = '<a href="{{UP}}pages/gigs.html" data-nav="gigs">Gigs &amp; Tours</a>'
    assert added.count(link) == 1
    last = text.rfind("</a>", 0, text.index("{{UP}}blog") if "{{UP}}blog" in text
                      else len(text)) + len("</a>")
    start = text.rfind("<a ", 0, last)
    space = text[len(text[:start].rstrip(" \t\n")):start]
    assert added == text[:last] + space + link + text[last:]


def test_add_refuses_a_menu_it_cannot_edit_safely():
    """INV-5: a menu of <ul><li> items is not plain, and add raises Unusual.

    Breaks when the link is pasted after the last </a>, inside an <li>."""
    with pytest.raises(menu.Unusual):
        menu.add(LISTED, "gigs", "Gigs")
    with pytest.raises(menu.Unusual):
        menu.remove(LISTED, "about")


def test_remove_takes_only_that_pages_links():
    """INV-6: every link to the page goes, with the whitespace before it, and
    nothing else; a link to about.html.bak is not a link to about.

    Breaks when the match is a substring rather than the whole value."""
    twice = FOUR.replace(
        '      <a href="{{UP}}blog',
        '      <a href="{{UP}}pages/about.html" data-nav="about">About again</a>\n'
        '      <a href="{{UP}}pages/about.html.bak">Old</a>\n'
        '      <a href="{{UP}}blog')
    removed = menu.remove(twice, "about")
    assert "pages/about.html\"" not in removed
    assert '<a href="{{UP}}pages/about.html.bak">Old</a>' in removed
    assert removed == FOUR.replace(
        '\n      <a href="{{UP}}pages/about.html" data-nav="About">About</a>', ""
    ).replace('      <a href="{{UP}}blog',
              '      <a href="{{UP}}pages/about.html.bak">Old</a>\n'
              '      <a href="{{UP}}blog')
    assert menu.remove(FOUR, "gigs") == FOUR


def test_rename_repoints_any_menu():
    """INV-7: the href changes; the words only where they are one of
    old_words; data-nav is left; a <ul><li> menu is edited too.

    Breaks when rename checks for a plain menu, or rewrites data-nav."""
    renamed = menu.rename(FOUR, "music", "songs", ("Music",), "Songs")
    assert renamed == FOUR.replace(
        '<a href="{{UP}}pages/music.html" data-nav="Music">Music</a>',
        '<a href="{{UP}}pages/songs.html" data-nav="Music">Songs</a>')

    kept = menu.rename(FOUR, "music", "songs", ("Tunes",), "Songs")
    assert '<a href="{{UP}}pages/songs.html" data-nav="Music">Music</a>' in kept

    listed = menu.rename(LISTED, "about", "story", ("About",), "Our story")
    assert listed == LISTED.replace('<a href="{{UP}}pages/about.html">About</a>',
                                    '<a href="{{UP}}pages/story.html">Our story</a>')


def test_a_commented_out_link_is_not_a_link():
    """§ 4.2: a link inside a comment is not one, so it is neither removed
    nor counted. Breaks when the comments are not blanked before matching."""
    text = ONE_LINE.replace("</nav>", '<!-- <a href="{{UP}}pages/about.html">x</a> --></nav>')
    assert menu.links_to(text, "about") == (menu.links_to(ONE_LINE, "about")[0],)
    assert "<!-- <a href" in menu.remove(text, "about")
