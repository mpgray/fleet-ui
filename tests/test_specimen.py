"""The specimen page Pin Preview screenshots.

These run without a browser. The screenshots happen in toolbox's `visual`
suite; what can be checked here is that the page it photographs is the page it
is supposed to be — every preset renders, every section the report names is on
it, and nothing on it can differ between two renders for a reason that is not
the pin. Run with `python -m pytest tests` (needs jinja2).
"""

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'python'))

import pytest  # noqa: E402

from fleet_specimen import SECTIONS, SPECIMEN, presets, render  # noqa: E402

PRESETS = presets(ROOT)


def test_every_preset_file_is_a_preset():
    """A glob that found nothing would parametrise the visual suite over zero
    presets, and zero presets is a green run."""
    assert len(PRESETS) == len(list((ROOT / 'css' / 'themes').glob('*.css'))) > 0


@pytest.mark.parametrize('preset', PRESETS)
def test_every_preset_renders_with_its_own_theme(preset):
    html = render(ROOT, preset, css_href='css')
    assert f'href="css/themes/{preset}.css"' in html
    assert 'href="css/site.css"' in html


def test_every_section_the_report_names_is_on_the_page_in_order():
    """The section name IS the report's "where". A section missing from the
    page is never screenshotted, so a change to it is never reported."""
    html = render(ROOT, PRESETS[0])
    found = re.findall(r'data-specimen="([a-z-]+)"', html)
    assert tuple(found) == SECTIONS


def test_the_page_has_no_script_and_requests_nothing_remote():
    """A remote request is a difference between two renders that the pin did
    not cause (and on a blog, a script is a policy breach: articles-ai's
    no-JavaScript test reads vendor/fleet-ui/templates too)."""
    html = render(ROOT, PRESETS[0])
    assert '<script' not in html.lower()
    # Anchors may point anywhere (the fleet links do, and nothing follows
    # them); what the browser fetches by itself may not.
    assert not re.search(r'src="(https?:)?//', html)
    assert not re.search(r'<link[^>]*href="(https?:)?//', html)


def test_the_page_renders_identically_twice():
    assert render(ROOT, PRESETS[0]) == render(ROOT, PRESETS[0])


def test_an_older_tree_borrows_the_newer_page(tmp_path):
    """The side of a preview from before the specimen existed has no page of
    its own; it must still render, from its OWN macros."""
    old = tmp_path / 'old'
    shutil.copytree(ROOT / 'templates', old / 'templates')
    shutil.copytree(ROOT / 'css' / 'themes', old / 'css' / 'themes')
    (old / SPECIMEN).unlink()
    # Mark the old tree's macro so the test can see whose macro rendered.
    header = old / 'templates' / 'macros' / 'header.html'
    header.write_text(header.read_text().replace('class="nav-toggle"', 'class="nav-toggle old-tree"'))

    html = render(old, PRESETS[0], specimen_tree=ROOT)
    assert 'old-tree' in html


def test_a_macro_the_older_tree_lacks_fails_loudly(tmp_path):
    """Rendering it as nothing would make both sides "match" on a section that
    one of them cannot draw."""
    old = tmp_path / 'old'
    shutil.copytree(ROOT / 'templates', old / 'templates')
    (old / SPECIMEN).unlink()
    fleet = old / 'templates' / 'macros' / 'fleet.html'
    fleet.write_text(fleet.read_text().replace('macro fleet_nav_split', 'macro renamed_away'))
    with pytest.raises(Exception):
        render(old, PRESETS[0], specimen_tree=ROOT)
