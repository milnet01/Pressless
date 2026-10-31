"""What a bring-in says it did (PRESS-0125 § 4.8, PRESS-0210 § 4.12): the Report
as lines of words, on a page and in import/report.txt. Its own module because
both Import's wizards and setup's Finish show it, and `importing` imports `setup`.
"""
from __future__ import annotations

import html
from pathlib import Path

import pressless_import
from pressless import safe_write
from pressless.words import say

_REPORT = "report.txt"


def shown(text: str) -> str:
    """A value from the export or the folder, as a page shows it: control
    characters escaped, then HTML-escaped (§ 4.8)."""
    return html.escape(pressless_import.printable(text))


def counted(count: int | str, one: str, many: str) -> str:
    """A count with its noun, which takes the singular for one (PRESS-0294)."""
    return say(one) if int(count) == 1 else say(many, count=str(count))


def _counts(report: pressless_import.Report) -> str:
    photographs = counted(report.photographs, "import.count.photographs.one",
                          "import.count.photographs.many")
    files = counted(report.files, "import.count.files.one", "import.count.files.many")
    if report.folder:
        return say("import.report.counts.folder", photographs=photographs, files=files)
    return say(
        "import.report.counts",
        published=counted(report.published, "import.count.published.one",
                          "import.count.published.many"),
        drafts=counted(report.drafts, "import.count.drafts.one", "import.count.drafts.many"),
        comments=counted(report.comments, "import.count.comments.one",
                         "import.count.comments.many"),
        photographs=photographs, files=files)


def lines(report: pressless_import.Report) -> list[str]:
    """§ 4.8: the Report as lines of words, each value as it was given."""
    said = [_counts(report), say("import.report.pages", pages=", ".join(report.pages))]
    if report.menus:
        said.append(say("import.report.menu", menu=report.menus[0]))
        if report.menus[1:]:
            said.append(say("import.report.other_menus", menus=", ".join(report.menus[1:])))
    said += [say("import.report.scheduled", slug=slug, date=when) if when
             else say("import.report.review", slug=slug) for slug, when in report.waiting]
    said += [say("import.report.moved", path=path, name=name) for path, name in report.moved]
    said += [say("import.report.unfetched", place=place, why=why)
             for place, why in report.unfetched]
    said += [say("import.report.renamed", wanted=wanted, given=given)
             for wanted, given in report.renamed_slugs]
    said += [say("import.report.renamed_file", place=place, name=name)
             for place, name in report.renamed_photographs]
    said += [say("import.report.inside", path=path) for path in report.inside_pages]
    said += [say("import.report.sheet_for_some", path=path) for path in report.sheets_for_some]
    said += [say("import.report.other_type.one", kind=kind) if count == 1
             else say("import.report.other_type.many", kind=kind, count=str(count))
             for kind, count in report.other_types]
    said += [say("import.report.dropped", where=dropped.slug, what=dropped.what)
             for dropped in report.dropped]
    return said


def keep(held: Path, said: list[str]) -> None:
    """The Report beside the import's other files, as import/report.txt."""
    safe_write.write_whole(held / _REPORT, "\n".join(
        pressless_import.printable(line) for line in said) + "\n", prefix=".report-")


def rows(said: list[str]) -> str:
    """The Report's lines as a list a page shows."""
    return ('<ul class="import-report">'
            + "".join(f"<li>{shown(line)}</li>" for line in said) + "</ul>")


def page(said: list[str]) -> str:
    return (f"<h1>{say('import.report.title')}</h1><p>{say('import.report.about')}</p>"
            + rows(said) + f'<p><a href="/">{say("setup.onward")}</a></p>')
