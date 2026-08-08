# fleet-ui

Shared visual layer for the site fleet. Every public-facing site — the blogs in
`articles-ai` and every extension site such as `game-db` — renders from these
files so that structural CSS cannot fork.

This repo exists to answer one question: *if I change the site style, do I have
to change it in two places?* No. You change it here, once.

## What's in here

```
css/site.css          structural styles — layout, header, cards, article body
css/themes/*.css      one file per theme preset; each defines the token block
templates/macros/     cards.html (article_card, byline, avatar), icons.html
templates/partials/   icon_sprite.html — self-hosted inline SVG sprite
```

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

## Known issues inherited from the extraction

Left as-is so the initial extraction stays byte-identical. Fix these once
`articles-ai` is consuming the submodule and the regression diff has passed:

- **Fonts load via `@import` inside each theme file**, creating a serial
  request chain — the browser can't discover the font until the theme CSS has
  parsed. Should become `<link rel="preconnect">` + `<link>` in `<head>`.
- **No cache-busting** on `site.css` or the theme files; a CSS change relies on
  browser and proxy revalidation. Needs a build-hash query string.
- **Zero media queries.** Responsiveness is emergent from `clamp()`,
  `grid auto-fill minmax()`, `flex-wrap` and `max-width`. It holds up for prose
  and card grids; it will not hold up for wide content such as stat tables, so
  consumers rendering those must supply their own `overflow-x: auto` containers
  and breakpoints.
# fleet-ui
# fleet-ui
# fleet-ui
