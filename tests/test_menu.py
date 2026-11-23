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
    return {"starter": starter.navigation(), "one line": ONE_LINE, "four": FOUR}


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



@pytest.mark.parametrize("kind", ["one line", "four"])
def test_add_puts_home_first_and_once(kind):
    """PRESS-0423: Home's link goes before the first link, at the site's root,
    followed by the whitespace before that link; a menu already linking Home
    is unchanged. Breaks when Home goes under pages/, last, or twice."""
    text = _menus()[kind]
    first = text.index("<a ")
    without = text[:first] + text[text.index("</a>") + len("</a>"):].lstrip(" \n")
    first_link = without.index("<a ")
    space = without[len(without[:first_link].rstrip(" \t\n")):first_link]
    link = '<a href="{{UP}}index.html" data-nav="Home">Home</a>'
    assert menu.add(without, "index", "Home") == (without[:first_link] + link + space
                                                  + without[first_link:])
    assert menu.add(text, "index", "Home") == text

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


def test_rename_reads_a_links_visible_words():
    """INV-7, PRESS-0328. Breaks when rename compares a link's raw inside, so
    words wrapped in a tag show in the menu view but are never renamed."""
    wrapped = ('<nav><a href="{{UP}}pages/about.html" data-nav="about">\n'
               '  <span>About &amp; us</span>\n</a></nav>')
    renamed = menu.rename(wrapped, "about", "story", ("About & us",), "Our <story>")
    assert renamed == ('<nav><a href="{{UP}}pages/story.html" data-nav="about">\n'
                       '  Our &lt;story&gt;\n</a></nav>')


def test_a_commented_out_link_is_not_a_link():
    """§ 4.2: a link inside a comment is not one, so it is neither removed
    nor counted. Breaks when the comments are not blanked before matching."""
    text = ONE_LINE.replace("</nav>", '<!-- <a href="{{UP}}pages/about.html">x</a> --></nav>')
    assert menu.links_to(text, "about") == (menu.links_to(ONE_LINE, "about")[0],)
    assert "<!-- <a href" in menu.remove(text, "about")


# ------------------------------------------------------------- PRESS-0216 ---

# A comment between links, a link with markup in its words, odd spacing.
ODD = ('<!-- top -->\n<nav class="m">\n  <a href="{{UP}}index.html" data-nav="Home">Home</a>'
       '\n   <!-- between -->\n\t<a href="{{UP}}pages/about.html" data-nav="about"><b>About</b>'
       ' us</a>\n  <a href="https://example.org/?a=1&amp;b=2">Shop</a>\n</nav>\n')


def _as_read(text: str) -> list[dict]:
    return [{"at": at, "words": words, "href": href}
            for at, (words, href) in enumerate(menu.links(text))]


def test_an_arranged_menu_keeps_every_other_byte():
    """PRESS-0216 INV-5. Breaks when the menu is written from its list of
    links rather than by moving each link's own bytes."""
    read = _as_read(ODD)
    assert read[1]["words"] == "About us" and read[2]["href"] == "https://example.org/?a=1&b=2"
    assert menu.arranged(ODD, read) == ODD
    moved = menu.arranged(ODD, [read[2], read[0], read[1]])
    assert moved == ('<!-- top -->\n<nav class="m">\n  <a href="https://example.org/?a=1&amp;b=2">'
                     'Shop</a>\n   <!-- between -->\n  <a href="{{UP}}index.html" data-nav="Home">'
                     'Home</a>\n\t<a href="{{UP}}pages/about.html" data-nav="about"><b>About</b>'
                     ' us</a>\n</nav>\n')


def test_a_changed_or_new_link_carries_its_page_name():
    """PRESS-0216 § 4.4. Breaks when a link sent to another page keeps the old
    page's data-nav, or Home is written under pages/."""
    read = _as_read(ODD)
    read[1] = {"at": 1, "words": "Contact", "href": "{{UP}}pages/contact.html"}
    read[2] = {"at": 2, "words": "Shop", "href": "https://example.org/"}
    new = {"at": None, "words": "Start", "href": "{{UP}}index.html"}
    written = menu.arranged(ODD, [*read, new])
    assert '<a href="{{UP}}pages/contact.html" data-nav="contact"><b>Contact</b></a>' not in written
    assert '<a href="{{UP}}pages/contact.html" data-nav="contact">Contact</a>' in written
    assert '<a href="https://example.org/">Shop</a>' in written
    assert '\n  <a href="{{UP}}index.html" data-nav="Home">Start</a>\n</nav>' in written



def test_every_edit_writes_a_links_words_alike():
    """Breaks when the menu view and Add or Rename escape a link's words
    differently, so one edit writes a quote bare and another as &quot;."""
    words = 'Tom & "Jo"'
    escaped = 'Tom &amp; &quot;Jo&quot;'
    assert f">{escaped}</a>" in menu.add(ONE_LINE, "gigs", words)
    assert f">{escaped}</a>" in menu.rename(ONE_LINE, "about", "gigs", ("About",), words)
    changed = [{"at": 0, "words": "Home", "href": "{{UP}}index.html"},
               {"at": 1, "words": words, "href": "{{UP}}pages/about.html"},
               {"at": None, "words": words, "href": "{{UP}}pages/gigs.html"}]
    assert menu.arranged(ONE_LINE, changed).count(f">{escaped}</a>") == 2

@pytest.mark.parametrize("posted", [
    [{"at": 7, "words": "Home", "href": "{{UP}}index.html"}],
    [{"at": 0, "words": "Home", "href": "{{UP}}index.html"},
     {"at": 0, "words": "Home", "href": "{{UP}}index.html"}],
    [{"at": None, "words": "  ", "href": "{{UP}}index.html"}],
    [{"at": None, "words": "Run", "href": "javascript:alert(1)"}],
    [{"at": 0, "words": " ", "href": "{{UP}}index.html"}],
    [{"at": 0, "words": "Home", "href": "javascript:alert(1)"}],
    [],
    "not a list",
])
def test_a_menu_post_naming_no_link_is_refused(posted):
    """PRESS-0216 § 4.4. Breaks when a bad entry is skipped and the rest written,
    or a post with no links writes a menu the menu view can no longer open."""
    with pytest.raises(menu.Refused):
        menu.arranged(ODD, posted)


# A logo link has no words, and a phone link an address no new link may take.
KEPT = ('<nav><a href="{{UP}}index.html" data-nav="Home"><img src="logo.png" alt=""></a> '
        '<a href="tel:+15550100">Call us</a> '
        '<a href="{{UP}}pages/about.html" data-nav="about">About</a></nav>')


def test_a_link_posted_back_as_it_was_given_is_kept():
    """PRESS-0216 § 4.4: an entry posted back as it was given is unchanged,
    so a menu the view opened can always be saved. Only what a save changes
    is checked. Breaks when a kept link with no words, or with an address a
    new link may not take, refuses every save of its menu."""
    read = _as_read(KEPT)
    assert read[0]["words"] == "" and read[1]["href"] == "tel:+15550100"
    assert menu.arranged(KEPT, read) == KEPT
    moved_up = menu.arranged(KEPT, [read[2], read[0], read[1]])
    assert moved_up.index("About</a>") < moved_up.index("logo.png") < moved_up.index("tel:")
    moved = {"at": 0, "words": "", "href": "{{UP}}pages/about.html"}
    assert ('<a href="{{UP}}pages/about.html" data-nav="about"><img src="logo.png" alt=""></a>'
            in menu.arranged(KEPT, [moved, read[1], read[2]]))


def test_a_page_address_reads_back_as_its_page():
    """The menu panel offers menu.address for each page. Breaks when it and
    _nav disagree, so a link picked from the list loses its data-nav."""
    assert menu.address("index") == "{{UP}}index.html"
    assert menu.address("about") == "{{UP}}pages/about.html"
    assert menu._nav(menu.address("index")) == "Home"
    assert menu._nav(menu.address("about")) == "about"


def test_a_journal_link_carries_the_journal_marker():
    """PRESS-0298, PRESS-0216 § 4.4. Breaks when a journal link added or
    pointed at the journal in the menu view gets no data-nav, so the
    journal's pages mark no link current."""
    posted = [{"at": 0, "words": "Home", "href": "{{UP}}index.html"},
              {"at": 1, "words": "About", "href": "{{UP}}blog/index.html"},
              {"at": None, "words": "Journal", "href": "{{UP}}blog/index.html"}]
    written = menu.arranged(ONE_LINE, posted)
    assert '<a href="{{UP}}blog/index.html" data-nav="Journal">About</a>' in written
    assert '<a href="{{UP}}blog/index.html" data-nav="Journal">Journal</a>' in written


@pytest.mark.parametrize("start_tag", [
    '<a data-href="x" href="{{UP}}pages/about.html">',
    '<a xlink:href="x" href="{{UP}}pages/about.html">',
    '<a title="its href=\'x\' is old" href="{{UP}}pages/about.html">',
])
def test_a_links_href_is_its_own_attribute(start_tag):
    """Only the attribute named href is a link's address: not data-href, not
    xlink:href, not href= written inside another attribute's value. Breaks
    when the first `href=` in the tag is taken, so the link is missed and
    the wrong attribute rewritten."""
    text = f"<nav>{start_tag}About</a> <a href=\"{{{{UP}}}}index.html\">Home</a></nav>"
    assert menu.links_to(text, "about")
    renamed = menu.rename(text, "about", "story", ("About",), "Story")
    assert start_tag.replace("pages/about.html", "pages/story.html") in renamed
    assert menu.links(text)[0] == ("About", "{{UP}}pages/about.html")
    moved = menu.arranged(text, [{"at": 0, "words": "About", "href": "{{UP}}pages/a.html"},
                                 {"at": 1, "words": "Home", "href": "{{UP}}index.html"}])
    assert start_tag.split(" href=")[0] in moved and 'href="{{UP}}pages/a.html"' in moved
