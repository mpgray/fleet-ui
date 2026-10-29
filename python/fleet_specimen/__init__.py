"""Render the fleet-ui specimen page for one theme preset, from any fleet-ui tree.

The specimen (templates/specimen/specimen.html) is every shared component once,
under one preset. It is what Pin Preview screenshots: toolbox's `visual` suite
renders it from the commit a consumer is pinned to and from the commit a pin
bump would move it to, and compares the two section by section.

Why the template and the tree are separate arguments
----------------------------------------------------
A preview compares two TREES (old pin, new pin) but must render one PAGE. If
each tree rendered its own copy of the specimen, adding a section to it would
read as "every preset changed" — a difference in the fixture, not the pin. So
the specimen markup comes from one place (`specimen_tree`, normally the newer
of the two) and everything it imports — the header and fleet macros, the icon
sprite — comes from the tree under test. The page is the constant; the code
under it is what moves.

That also means a tree from before the specimen existed can still be previewed:
the older side borrows the newer side's page.

jinja2 is the one dependency, and every consumer already has it through Flask.
Never imported by a running site.
"""

from __future__ import annotations

from pathlib import Path

SPECIMEN = Path('templates') / 'specimen' / 'specimen.html'

# The report's words for "where", in page order. Each is a `[data-specimen]`
# element in the template; tests/test_specimen.py holds the two in step.
SECTIONS = ('header', 'article', 'cards', 'tables', 'forms', 'footer')


def presets(tree: str | Path) -> list[str]:
    """Every theme preset a fleet-ui tree ships, sorted."""
    return sorted(p.stem for p in (Path(tree) / 'css' / 'themes').glob('*.css'))


def render(tree: str | Path, preset: str, css_href: str = 'css',
           specimen_tree: str | Path | None = None) -> str:
    """The specimen HTML for `preset`, with macros and sprite from `tree`.

    `css_href` is the URL prefix of `tree`'s css/ directory as seen from
    wherever the page will be served. `specimen_tree` supplies the page itself
    and defaults to `tree`.
    """
    from jinja2 import Environment, FileSystemLoader, StrictUndefined

    tree = Path(tree)
    source = (Path(specimen_tree or tree) / SPECIMEN).read_text()
    # StrictUndefined: a macro the older tree does not have must fail loudly,
    # not render as an empty string that then "matches" on both sides.
    env = Environment(loader=FileSystemLoader(str(tree / 'templates')),
                      autoescape=True, undefined=StrictUndefined)
    return env.from_string(source).render(preset=preset, css_href=css_href)
