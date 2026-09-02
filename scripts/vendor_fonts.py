"""Vendor every face the presets name, from Fontsource, into css/fonts/.

Run from the repo root:
    python scripts/vendor_fonts.py            # sync css/fonts/ to the presets
    python scripts/vendor_fonts.py --check    # fail if it is out of sync; write nothing

WHY THE FACES ARE VENDORED AT ALL. Each preset used to `@import` its typefaces
from `fonts.googleapis.com`, so every reader's browser called Google on every
page load and Google received their IP address. That was undisclosed on all
twenty-six blogs until the privacy policy was rewritten to name it. Serving the
faces ourselves removes the third party rather than disclosing it, which is the
only version of that fix that cannot rot.

It also removes a render-blocking chain the consumers cannot avoid: stylesheet
-> `@import` -> Google DNS + TLS -> font. Cloudflare strips the `preconnect`
hints that used to soften it (it rewrites Google Fonts *links in HTML*, and an
`@import` inside a CSS file is invisible to that), so the chain is currently
paid in full with no mitigation.

THE PRESETS ARE THE SOURCE OF TRUTH. There is no list of families in this file
to keep in step with anything. The script reads `--font-body` and
`--font-heading` out of every preset, vendors exactly those families, and
deletes the files of any family no longer named. So:

    add a font       edit the preset's --font-heading; this runs in CI
    retire a font    edit the preset; this deletes the orphaned files
    add a weight     nothing — every published weight is already vendored
    add a preset     nothing, unless it names a family no other preset uses

WHY FONTSOURCE AND NOT GOOGLE DIRECTLY. Google's CSS API varies its answer by
User-Agent and returns opaque, versioned gstatic URLs; scraping it means owning
the subsetting, the `unicode-range` descriptors and the `@font-face` authoring
by hand, and re-owning them whenever the API changes. Fontsource publishes the
same faces already subset, already split per unicode range, with the
`@font-face` blocks written and `font-display: swap` set — and its built files
are fetchable over plain HTTP from a CDN, so this stays a Python script in a
repo with no Node toolchain.

WHY THE RANGES ARE FETCHED TOO. Fontsource's per-subset stylesheets
(`latin.css`, `latin-ext.css`) carry no `unicode-range` — they are built to be
used ONE AT A TIME. This script concatenates them, so without a range two
`@font-face` rules declare the same family, weight and style, and a browser has
no way to know which file holds which characters until it has fetched them.

The text still renders: font matching falls through to the next face in the
same family, so latin-ext is tried, misses every ASCII letter, and latin is used.
What it costs is the download. Measured on a page of pure ASCII, the rangeless
build fetches BOTH spectral-latin-ext-400 and spectral-latin-400; the stamped
build fetches only latin. That is roughly double the font bytes on every page,
for a file with no glyph the page can use — and it is fetched first, so
`font-display: swap` holds the fallback face on screen longer than it needs to.

Which is exactly the saving the docstring above claims for splitting subsets:
"a reader pulls the same latin file whether four files were vendored for a
family or forty" is only true once the ranges are there to be pulled by. The
package's own `index.css` publishes the range per subset, so it is fetched and
each block is stamped with the one it needs.

WHY EVERY WEIGHT AND EVERY SUBSET. Disk is paid once; page weight is not paid at
all. The files are split per unicode range, so a browser downloads only the
subsets it actually renders — a reader pulls the same latin file whether four
files were vendored for a family or forty. Vendoring the full set is what makes
"add a weight" cost nothing, which is what keeps this off anyone's plate.
"""

import argparse
import json
import pathlib
import re
import shutil
import sys
import urllib.error
import urllib.request

CDN = 'https://cdn.jsdelivr.net/npm'
REGISTRY = 'https://registry.npmjs.org'
UA = {'User-Agent': 'fleet-ui-vendor-fonts'}

# Subsets to vendor. Each is a separate file with its own unicode-range, so
# listing more costs disk and never costs a reader a byte they do not render.
# 'latin' alone would drop an accented name mid-word with no error anywhere.
SUBSETS = ('latin', 'latin-ext')

# A family named in a preset but not published under this slug is an error, not
# a skip: skipping quietly is how a page ends up rendering in Times.
SLUG_OVERRIDES: dict[str, str] = {}

_FONT_DECL = re.compile(r'--font-(?:body|heading)\s*:\s*([^;]+);')
_FIRST_FAMILY = re.compile(r"^\s*(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z0-9 ]+?))\s*(?:,|$)")
_SRC_URL = re.compile(r"url\(\.?/?(files/[^)]+?\.woff2)\)")


def families_in_presets(root: pathlib.Path) -> dict[str, list[str]]:
    """Every family the presets name, mapped to the presets naming it.

    Only the FIRST family in each declaration is vendored. The rest of the stack
    is the fallback chain — `system-ui`, `Georgia`, `sans-serif` — which is the
    whole point of a fallback and must never be downloaded.
    """
    found: dict[str, list[str]] = {}
    themes = sorted((root / 'css' / 'themes').glob('*.css'))
    if not themes:
        sys.exit(f'No presets found under {root / "css" / "themes"}.')
    for path in themes:
        for decl in _FONT_DECL.findall(path.read_text()):
            match = _FIRST_FAMILY.match(decl.strip())
            if not match:
                continue
            family = next(g for g in match.groups() if g)
            if family.lower() in ('system-ui', 'ui-sans-serif', 'ui-serif',
                                  'ui-monospace', 'sans-serif', 'serif', 'monospace'):
                continue
            found.setdefault(family, []).append(path.name)
    return found


def slug(family: str) -> str:
    """'Zilla Slab' -> 'zilla-slab', Fontsource's package name."""
    if family in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[family]
    return re.sub(r'[^a-z0-9]+', '-', family.lower()).strip('-')


def _get(url: str, timeout: int = 30) -> bytes:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout).read()


def latest_version(package: str) -> str:
    try:
        return json.loads(_get(f'{REGISTRY}/@fontsource/{package}/latest'))['version']
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(
                f'No Fontsource package "@fontsource/{package}". A preset names a '
                f'family that resolves to that slug and nothing publishes it — fix '
                f'the preset, or add the real slug to SLUG_OVERRIDES in this file. '
                f'Not skipped: a missing face renders as Times in production.')
        raise


# Both licences these faces ship under require the notice to travel with the
# files, so it is fetched alongside them rather than left as a promise in a
# README. Every Fontsource package declares one and ships the upstream text.
LICENCE_FILENAMES = ('LICENSE', 'LICENSE.md', 'license')


def fetch_licence(package: str, version: str, family_dir: pathlib.Path) -> str:
    """Save the upstream licence beside the faces. Returns its SPDX id."""
    spdx = json.loads(_get(f'{REGISTRY}/@fontsource/{package}/{version}')).get('license', '')
    for name in LICENCE_FILENAMES:
        try:
            (family_dir / 'LICENSE').write_bytes(
                _get(f'{CDN}/@fontsource/{package}@{version}/{name}'))
            return spdx
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
    raise SystemExit(
        f'@fontsource/{package} ships no licence file. These faces are '
        f'redistributed in this repo and both OFL-1.1 and Apache-2.0 require '
        f'the notice to accompany them — not vendored without it.')


# A subset's range lives only in the package's combined `index.css`. The
# per-subset files this script concatenates do not carry one, and the file name
# is the only thing tying a rule back to its subset.
_INDEX_FILE = r'{package}-(.+)-\d+-(?:normal|italic)\.woff2'
_RANGE = re.compile(r'unicode-range:\s*([^;]+);')


def subset_ranges(package: str, version: str) -> dict[str, str]:
    """{subset: unicode-range} for one family, read off its own index.css.

    Taken from the package rather than hardcoded here: the ranges are Google's
    and they do change (U+1C80-1C8A joined cyrillic-ext in 2024). A constant in
    this file would drift silently, and drift in a `unicode-range` shows up as
    one accented character in the wrong face — the kind of thing nobody reports.
    """
    css = _get(f'{CDN}/@fontsource/{package}@{version}/index.css').decode()
    name = re.compile(_INDEX_FILE.format(package=re.escape(package)))
    ranges: dict[str, str] = {}
    for block in css.split('@font-face'):
        found, rng = name.search(block), _RANGE.search(block)
        if found and rng:
            ranges.setdefault(found.group(1), rng.group(1).strip())
    if not ranges:
        raise SystemExit(
            f'@fontsource/{package}@{version} published no unicode-range in its '
            f'index.css. Vendoring the subsets without one makes every reader '
            f'download all of them on every page.')
    return ranges


def vendor_family(family: str, out_root: pathlib.Path) -> tuple[str, int]:
    """Download one family's CSS and woff2 files. Returns (version, file count).

    The CSS is rewritten so `url(./files/x.woff2)` becomes `url(x.woff2)`,
    flattening Fontsource's layout into one directory per family. The `.woff`
    fallbacks are dropped: every browser that reaches these sites has supported
    woff2 for years, and keeping them would roughly double what is committed.
    """
    package = slug(family)
    version = latest_version(package)
    family_dir = out_root / package
    family_dir.mkdir(parents=True, exist_ok=True)
    ranges = subset_ranges(package, version)

    blocks, files = [], 0
    for subset in SUBSETS:
        try:
            css = _get(f'{CDN}/@fontsource/{package}@{version}/{subset}.css').decode()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue          # not every family publishes every subset
            raise
        for rel in sorted(set(_SRC_URL.findall(css))):
            name = rel.split('/')[-1]
            target = family_dir / name
            if not target.exists():
                target.write_bytes(_get(f'{CDN}/@fontsource/{package}@{version}/{rel}'))
            files += 1
        # Drop the woff fallback from each src, and flatten the path.
        css = re.sub(r",\s*url\([^)]*\.woff\)\s*format\('woff'\)", '', css)
        css = _SRC_URL.sub(lambda m: f'url({m.group(1).split("/")[-1]})', css)
        # Stamp every rule with its subset's range. Without it the blocks are
        # indistinguishable on (family, weight, style) and every reader pays for
        # every subset — see WHY THE RANGES ARE FETCHED TOO at the top.
        rng = ranges.get(subset)
        if rng is None:
            raise SystemExit(
                f'@fontsource/{package}@{version} ships a {subset}.css but names '
                f'no unicode-range for "{subset}" in its index.css. Emitting the '
                f'block anyway would make every reader download this subset on '
                f'every page whether or not a character in it appears.')
        css = re.sub(r'(\n\s*src:[^;]+;)',
                     lambda m, r=rng: f'{m.group(1)}\n  unicode-range: {r};', css)
        blocks.append(f'/* --- {subset} --- */\n{css.strip()}')

    if not files:
        raise SystemExit(f'@fontsource/{package} published no {"/".join(SUBSETS)} '
                         f'woff2 files. Check the family name in the preset.')
    spdx = fetch_licence(package, version, family_dir)
    (family_dir / 'index.css').write_text(
        f'/* {family} — vendored from @fontsource/{package}@{version}.\n'
        f'   Licence: {spdx} (see LICENSE beside this file).\n'
        f'   Generated by scripts/vendor_fonts.py. Do not edit by hand. */\n\n'
        + '\n\n'.join(blocks) + '\n')
    return version, files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--check', action='store_true',
                        help='fail if css/fonts/ is out of sync; write nothing')
    parser.add_argument('--root', default='.', help='repo root')
    args = parser.parse_args()

    root = pathlib.Path(args.root).resolve()
    fonts_dir = root / 'css' / 'fonts'
    wanted = families_in_presets(root)
    want_slugs = {slug(f) for f in wanted}
    have_slugs = {p.name for p in fonts_dir.iterdir() if p.is_dir()} if fonts_dir.is_dir() else set()

    missing = sorted(want_slugs - have_slugs)
    orphans = sorted(have_slugs - want_slugs)

    if args.check:
        # Membership only. Byte-comparing would re-download every family on
        # every CI run and turn a Fontsource patch release into a red build on
        # a PR that never touched a font.
        problems = []
        if missing:
            problems.append('presets name families with no vendored files: '
                            + ', '.join(missing))
        if orphans:
            problems.append('vendored families no preset names any more: '
                            + ', '.join(orphans))
        # Membership is not enough: a directory can exist while the @font-face
        # inside it points at a file that is not there. That failure is silent
        # in a browser — it falls back down the stack and the page just renders
        # in Georgia — so it has to be caught by arithmetic here.
        broken = []
        for theme in sorted((root / 'css' / 'themes').glob('*.css')):
            for rel in re.findall(r"@import url\('(\.\./fonts/[^']+)'\)", theme.read_text()):
                target = (theme.parent / rel).resolve()
                if not target.is_file():
                    broken.append(f'{theme.name} imports {rel}, which does not exist')
                    continue
                for face in re.findall(r'url\(([^)]+\.woff2)\)', target.read_text()):
                    if not (target.parent / face).is_file():
                        broken.append(f'{target.name} references {face}, which does not exist')
        if broken:
            problems.append('font references that do not resolve:\n      '
                            + '\n      '.join(broken[:10]))

        # A quieter failure than the one above, and the reason it needs a check
        # at all: nothing breaks. Every face resolves, every file is present,
        # the page renders correctly — and each reader downloads a subset file
        # holding no character the page uses, because without a range the
        # browser cannot tell the subsets apart. A rule without a range is only
        # safe when it is the only rule for its family, which is never true
        # here: this script always concatenates at least two subsets.
        rangeless = []
        for index in sorted(fonts_dir.glob('*/index.css')):
            faces = index.read_text().split('@font-face')[1:]
            bare = sum(1 for block in faces if 'unicode-range' not in block)
            if bare:
                rangeless.append(f'{index.parent.name}: {bare} of {len(faces)} '
                                 f'@font-face rules carry no unicode-range')
        if rangeless:
            problems.append('subsets that will collide and fall back:\n      '
                            + '\n      '.join(rangeless))

        # Nothing may reach Google any more. The faces are vendored precisely so
        # readers' browsers stop calling a third party, and one preset carrying
        # an @import undoes that for its whole site — and, because the families
        # are the same, does it invisibly.
        google = sorted(t.name for t in (root / 'css').rglob('*.css')
                        if 'fonts.googleapis.com' in t.read_text(errors='replace'))
        if google:
            problems.append('still fetching faces from Google: ' + ', '.join(google))

        unlicensed = sorted(
            name for name in (want_slugs & have_slugs)
            if not (fonts_dir / name / 'LICENSE').is_file())
        if unlicensed:
            problems.append('vendored without the licence notice they are '
                            'redistributed under: ' + ', '.join(unlicensed))
        if problems:
            print('css/fonts/ is out of sync with the presets:')
            for line in problems:
                print(f'  - {line}')
            print('\nRun: python scripts/vendor_fonts.py')
            sys.exit(1)
        print(f'css/fonts/ matches the presets ({len(want_slugs)} families).')
        return

    fonts_dir.mkdir(parents=True, exist_ok=True)
    for family in sorted(wanted):
        version, files = vendor_family(family, fonts_dir)
        note = '' if slug(family) in have_slugs else '  (new)'
        licence = (fonts_dir / slug(family) / 'LICENSE')
        print(f'  {family:<24} @{version:<8} {files:>3} woff2  '
              f'{"licence ok" if licence.exists() else "NO LICENCE"}{note}')
    for stale in orphans:
        shutil.rmtree(fonts_dir / stale)
        print(f'  {stale:<24} removed — no preset names it')
    print(f'\n{len(wanted)} families vendored, {len(orphans)} removed.')


if __name__ == '__main__':
    main()
