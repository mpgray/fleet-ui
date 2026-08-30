# fleet-ui

Shared visual layer for the site fleet. Every public-facing site — the blogs in
`articles-ai` and every extension site such as `game-db` — renders from these
files so that structural CSS cannot fork.

This repo exists to answer one question: *if I change the site style, do I have
to change it in two places?* No. You change it here, once.

## What's in here

```
css/site.css              structural styles — scales, layout, header, cards, article
css/themes/*.css          one file per theme preset; each defines the token block
css/tokens-bootstrap.css  the scales as --bs-* vars, for the Bootstrap-based
                          admin panel and writers' portal (no colours, opt-in)
templates/macros/         icons.html  — icon(name) -> <svg><use href="#icon-name">
                          header.html — nav_toggle(), nav_row() (the two rows)
                          fleet.html  — cross-links, split across those rows
templates/partials/       icon_sprite.html — self-hosted inline SVG sprite
css/fonts/<family>/       vendored woff2 faces + the @font-face CSS + LICENSE,
                          one directory per family. Generated — see below.
scripts/check_contrast.py CI: every preset clears WCAG AA. Runs standalone.
scripts/vendor_fonts.py   CI: syncs css/fonts/ to the families the presets name.
```

## Typefaces

The faces are **served from this repo**, not fetched from Google. A preset that
`@import`s from `fonts.googleapis.com` makes every reader's browser call Google
on every page load, which puts a third party between the consumer and its
readers and has to be disclosed in each one's privacy policy.

**The presets are the source of truth.** `scripts/vendor_fonts.py` reads
`--font-body` and `--font-heading` out of every preset, vendors exactly those
families from [Fontsource](https://fontsource.org), and deletes the files of any
family no longer named. There is no list to keep in step.

| You want to | You do |
|---|---|
| add a font | edit the preset's `--font-heading` |
| retire a font | edit the preset |
| add a weight | nothing — every published weight is vendored |
| add a preset using existing families | nothing |

CI runs the script on every pull request and **commits the result into your
branch**, so editing the preset is the whole job. It runs here rather than at
deploy time on purpose: consumers pin this repo by SHA and cache-bust their
stylesheets with that hash, so faces fetched at deploy time would not be the
bytes the pin identifies — and every consumer's deploy would grow a hard
dependency on an npm CDN being reachable.

Every family is vendored with all its published weights and both latin subsets.
That costs disk and costs a reader nothing: the files are split per
`unicode-range`, so a browser downloads only what it renders. Each family
directory carries the upstream `LICENSE` — these faces are redistributed here,
and both OFL-1.1 and Apache-2.0 require the notice to travel with them.

## The design

One signature: a hairline rule in `--accent` down the left of the article, with
the article's own structure hung off it — the eyebrow at the top, a tick at each
`h2`, a pull quote stepping out to take the rule over for its height. It is a
table of contents drawn in the margin, which is why it is allowed to exist: it
tells the reader how much is left and where the seams are.

That rule reappears as the band under the header, the foot of the hero and the
top edge of a card on hover. It is the reason `--accent` is the one token
carrying structure rather than decoration — and structure is the one thing that
survives being rendered in CRT green on a LAN party site and in dusty rose on a
wedding blog.

Everything else stays quiet so that it reads. **There are no drop shadows
outside the sticky header.** There used to be eight, every one a hardcoded
`rgba(0, 0, 0, α)`, which meant the four dark presets rendered flat while the
six light ones floated. The fleet did not share a look; it shared a stylesheet
that only worked on half of it.

### What does *not* belong here

Presentation is shared; **domain macros are not**. `article_card`, `byline` and
`writer_box` take article/author/writer dicts that exist only in `articles-ai`,
so they live there. A game database writes its own `entity_card` against the
same `.card` classes.

The test: if a macro's parameters name a concept only one consumer has, it is
not fleet code. Getting this wrong is expensive in a specific way — a blog
byline tweak would force a pin bump in every unrelated consumer.

## The token contract

`site.css` contains **no literal colors, fonts, or radii**. Every look-and-feel
value comes from a CSS custom property that a theme preset defines:

```
--bg  --surface  --text  --muted  --accent  --accent-contrast  --border
--font-body  --font-heading  --radius  --header-bg  --header-text
```

Twelve tokens, and that is the whole contract. A consumer that keeps these
names gets the fleet look for free by loading `site.css` plus one theme file.

Adding a token is a breaking change for every consumer — do it deliberately.
Adding a *theme preset* is not, and a new preset becomes available to blogs and
extension sites simultaneously.

CI enforces the number, not just the names: `required == CONTRACT` fails both
ways, so a thirteenth required token cannot arrive without someone editing the
list in a reviewable diff. That is the check, because a contract grows one
individually-reasonable token at a time.

### Scales are declared here, not by the presets

`site.css` also declares its own space, type, radius, elevation and measure
scales in `:root`. Those are **structure**, so they are this file's business,
not brand:

```
--step--2 … --step-4        type, a 1.2 scale off a 17px body
--space-1 … --space-8       4px base
--r-1 --r-2                 MULTIPLIED from --radius, never added to
--r-pill --r-circle         shapes, NOT degrees of rounding — see below
--rule --rule-accent --rule-spine
--shadow-color --elev-1
--measure --container --column
```

A preset may override any of them — the cascade puts it second — but it never
has to, so **adding a scale is not a breaking change for a consumer**. That is
why the CI job subtracts `site.css`'s own declarations before checking what it
requires of the presets.

Two of these are worth knowing about before you touch them:

- **`--r-*` multiply.** They used to be written `calc(var(--radius) + 8px)` in
  nine places, which inverted the token: `terminal` asks for `0` and got
  10px-rounded cards anyway, `valheim` asks for `14px` and got 24px pillows.
  Multiplying respects what the preset asked for at both ends of the range.
- **`--r-pill` and `--r-circle` do not scale off `--radius`, on purpose.** A
  pill is a pill and an avatar is a circle at every preset — those are shapes,
  and deriving them from a corner-softening token means `--radius: 0` silently
  turns a round logo into a square one nobody asked for. A preset that *does*
  want that overrides the two by name, which is a line in a diff someone reads.
  `terminal` is the one that does.
- **`--shadow-color` is expected to be overridden per preset.** No single value
  is right on both `#faf7f2` and `#060a06`; on a near-black background the
  honest answer is `transparent`, and `--elev-1` carries a border-coloured line
  that always renders so the header keeps a defined edge either way.

### Accessibility floor

`scripts/check_contrast.py` fails CI if any preset drops a text pair below
4.5:1. It exists because four of the ten shipped under AA on `--muted` and
nobody caught it: the value looks reasonable in a swatch, and `--muted` is
never the colour you are looking at when you review a preset — it is only the
colour of every excerpt, timestamp, caption, tagline and the entire footer.

`site.css` also carries one `:focus-visible` rule covering everything
interactive, a skip link, and a `prefers-reduced-motion` block at the foot of
the file (last, so it wins on specificity ties, and it reaches into the presets
— `terminal` animates a blinking cursor).

## Cascade order is load-bearing

Themes override `site.css` component rules at equal specificity, so `site.css`
must load **first** or the theme's flourishes are silently dead:

```
1. fleet-ui/css/site.css              structure
2. fleet-ui/css/themes/<preset>.css   token block + per-theme flourishes
3. <consumer>/…                       consumer-specific components, if any
4. /site-theme.css                    per-site token overrides, served at runtime
```

Step 4 comes from `articles-ai`, which owns the per-site token *values*. This
repo owns the code; `articles-ai` owns the values. Neither owns both.

## Consuming this repo

Vendor it as a git submodule pinned by SHA, and have the Dockerfile copy it in:

```bash
git submodule add https://github.com/mpgray/fleet-ui vendor/fleet-ui
```

Rules for consumers:

1. **Never fork these files into your repo.** If you need a component that
   isn't here, add it here, or layer a consumer-specific stylesheet *after*
   the theme file using only the twelve tokens.
2. **Report your pinned SHA** in your `/fleet/manifest` response. The
   `articles-ai` admin dashboard compares pins across the fleet and raises a
   drift alarm when they diverge.
3. **Bump deliberately.** A pin bump is a commit you can revert.

## Provenance

Extracted verbatim from `articles-ai/app/static/public/` and
`articles-ai/app/templates/` so the first extraction is a pure refactor with
byte-identical rendered output. `articles-ai` has not yet been switched over to
consume this repo — that is the second half of phase 0.

## Known issues

- **The presets still `@import` from Google as well as loading the vendored
  faces.** The faces are now served from this repo (see *Typefaces* above), but
  the old `@import` lines are deliberately still in place for one release so the
  self-hosted files can be verified rendering in production before anything
  depends on them alone. Until they come out, a reader's browser still calls
  Google and the blogs' privacy policies still disclose it — the disclosure is
  derived from these files, so it retires itself when the imports do.

Resolved since the extraction, listed so a reader of an old branch knows:

- ~~Consumers emit `preconnect` for the Google Fonts hosts, but the serial
  request chain remains~~ — the faces are vendored here now. Worth knowing why
  the `preconnect` mitigation had stopped working at all: Cloudflare fronts
  every consumer domain and its Fonts feature rewrites Google Fonts **links in
  HTML**, so it stripped those hints while leaving the `@import` inside the CSS
  untouched. The chain was being paid in full with the mitigation removed.

- ~~No cache-busting~~ — consumers append `?v=<pinned sha>`, so the URL changes
  exactly when the stylesheet does.
- ~~Zero media queries, so wide content is the consumer's problem~~ —
  `.table-scroll` / `.stat-table` / `.article-body table` now live here, scroll
  container and breakpoints included. They were promoted from `game-db`, which
  had to own them because this file had no table rules at all; the same gap
  meant a markdown table in a blog article rendered unstyled, and `brewhouse`
  was patching `article table` on its own for recipes. Wide content was never
  one site's problem.

## CI and shipping

`ci.yml` parses every template and stylesheet, and checks that **every CSS
variable `site.css` uses is declared by every theme preset**. A `var()` with no
declaration renders as nothing, so the failure is a colour that silently
vanishes on one site — exactly the drift this repo exists to prevent, and not
something anyone notices from a diff.

Nothing here is deployed. A merge to `main` opens a pin-bump pull request in
`articles-ai` and `game-db` instead. That PR runs each consumer's own test
suite and gets its own review, which makes it the only point at which a change
to shared CSS is tested against a site that renders it. Merging one consumer's
PR and not the other's is what the drift alarm on the admin dashboard is for.

Requires `FLEET_PIN_TOKEN` (a PAT with write access to both consumers) and
`ANTHROPIC_API_KEY`. See `articles-ai/PIPELINE.md`.
