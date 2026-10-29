"""Write the specimen page for every theme preset, to open in a browser.

    python3 scripts/build_specimen.py            # -> build/specimen/index.html
    python3 scripts/build_specimen.py --out DIR

One HTML file per preset plus an index, linking this checkout's css/ by a
relative path, so the pages show exactly the working tree with no server: edit
a preset, re-run, reload. This is the by-hand half of Pin Preview; the
before/after comparison across a pin bump is toolbox's `visual` suite.

Needs jinja2 (`pip install jinja2`, as CI already does).
"""

import argparse
import os
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'python'))

from fleet_specimen import presets, render  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default=str(ROOT / 'build' / 'specimen'))
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    css_href = Path(os.path.relpath(ROOT / 'css', out)).as_posix()

    names = presets(ROOT)
    for name in names:
        (out / f'{name}.html').write_text(render(ROOT, name, css_href=css_href))
    items = '\n'.join(f'<li><a href="{escape(n)}.html">{escape(n)}</a></li>' for n in names)
    (out / 'index.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>fleet-ui specimen</title>'
        f'<h1>fleet-ui specimen</h1><p>{len(names)} presets.</p><ul>{items}</ul>\n')
    print(f'{len(names)} presets -> {out / "index.html"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
