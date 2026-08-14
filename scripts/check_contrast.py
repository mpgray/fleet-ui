"""Fail if any theme preset renders text under WCAG AA (4.5:1).

Run from the repo root: `python scripts/check_contrast.py`

This exists because four of the ten presets shipped below AA on `--muted` and
nobody noticed for the same reason nobody ever notices: the value looks
reasonable in a swatch, and `--muted` is never the colour you are looking at
when you review a preset. It is, however, the colour of every card excerpt,
hero excerpt, timestamp, figcaption, tagline and the whole footer — most of the
small type on the site.

Pairs are the ones that actually appear as text in site.css. `--accent` is
checked against both backgrounds because `a { color: var(--accent) }` puts it
in running prose, and `--accent-contrast` against `--accent` because that is
the label inside every filled button.
"""
import pathlib
import re
import sys

# (foreground token, background token, minimum ratio)
PAIRS = [
    ('--text', '--bg', 4.5),
    ('--muted', '--bg', 4.5),
    ('--accent', '--bg', 4.5),
    ('--text', '--surface', 4.5),
    ('--muted', '--surface', 4.5),
    ('--header-text', '--header-bg', 4.5),
    ('--accent-contrast', '--accent', 4.5),
]


def rgb(value, under=None):
    """Hex, or an rgba() composited over `under`.

    `valheim` is the one preset with a translucent --header-bg, and skipping
    non-hex values would silently exempt the only header whose real contrast
    cannot be read straight off the token.
    """
    text = value.strip()
    match = re.match(r'rgba?\(([^)]+)\)', text)
    if match:
        parts = [p.strip() for p in match.group(1).replace('/', ',').split(',')]
        r, g, b = (int(float(p)) for p in parts[:3])
        alpha = float(parts[3]) if len(parts) > 3 else 1.0
        if under is not None:
            ur, ug, ub = rgb(under)
            r = round(r * alpha + ur * (1 - alpha))
            g = round(g * alpha + ug * (1 - alpha))
            b = round(b * alpha + ub * (1 - alpha))
        return r, g, b
    digits = text.lstrip('#')
    if len(digits) == 3:
        digits = ''.join(c * 2 for c in digits)
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def luminance(value, under=None):
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb(value, under))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg, under=None):
    a, b = luminance(fg, under), luminance(bg, under)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def main(root='.'):
    themes = sorted(pathlib.Path(root, 'css/themes').glob('*.css'))
    if not themes:
        print('FAIL no theme presets found — wrong working directory?')
        return 1

    failed = False
    for theme in themes:
        declared = dict(re.findall(
            r'^\s*(--[\w-]+)\s*:\s*([^;]+);', theme.read_text(), re.M))
        for fg, bg, need in PAIRS:
            a, b = declared.get(fg, '').strip(), declared.get(bg, '').strip()
            if not a or not b:
                # The token job already fails on a missing declaration; do not
                # report the same problem twice with a different message.
                continue
            got = ratio(a, b, under=declared.get('--bg', '#ffffff'))
            if got < need:
                failed = True
                print(f'FAIL {theme.name}: {fg} on {bg} is {got:.2f}:1, '
                      f'needs {need} ({a} on {b})')

    print(f'{len(themes)} presets checked against {len(PAIRS)} text pairs')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
