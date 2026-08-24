# fleet-ui

Shared visual layer for the site fleet — see [README.md](README.md) for the full
picture (the design, the cascade order, what does and doesn't belong here).

## The rule that governs this repo

**`site.css` contains no literal colors, fonts, or radii.** Every look-and-feel
value comes from twelve CSS custom properties a theme preset defines:

```
--bg --surface --text --muted --accent --accent-contrast --border
--font-body --font-heading --radius --header-bg --header-text
```

Dropping one from a theme file doesn't fail anything locally — the affected
property just renders as nothing on every site using that preset, and nothing
in a diff calls that out. A `PreToolUse` hook (`.claude/hooks/guard-token-contract.sh`)
refuses an edit that would leave a theme file missing a required token; CI's
`scripts/check_contrast.py` covers the contrast half (WCAG AA), which the hook
does not attempt.

Adding a token is a breaking change for every consumer (articles-ai, game-db,
ai-help, toolbox) — do it deliberately, and see [[fleet-sync]] (the global
subagent) if the change needs to ripple into consumer repos.

## Quick facts

- Cascade order is load-bearing: `site.css` (structure) loads before the theme
  file (tokens + flourishes) loads before any consumer-specific stylesheet.
- Domain macros (`article_card`, `byline`, `entity_card`) do not live here —
  only presentation that no single consumer owns.
- Nothing here deploys on its own. A merge to `main` opens a pin-bump PR in
  articles-ai and game-db; that PR is the only point a shared-CSS change is
  actually tested against a rendering site.

## Before committing

```bash
uv run python scripts/check_contrast.py
```
