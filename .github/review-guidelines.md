# What a review of this repo is looking for

Read by Copilot via `.github/copilot-instructions.md`, and by the weekly audit.

This repo is shared CSS, theme presets and Jinja macros for every site in the
fleet. Nothing here is deployed. It reaches production by being pinned as a
submodule, which means a mistake here does not fail here — it fails in the four
repositories that vendor it (`articles-ai`, `game-db`, `toolbox`, `videogaming`),
at whatever later moment someone merges a pin bump. The `consumer:` matrix in
`bump-consumers.yml` is the authoritative list; `ai-help` renders fleet themes
with its CSS inline and is deliberately not one of them.

## The invariants

**Every variable `site.css` uses must be declared by every theme preset.** A
`var()` with no declaration renders as nothing, so the symptom is a colour
silently vanishing on one site. CI checks this; a PR that adds a token to
`site.css` must add it to all ten presets.

**Structural CSS here, values in the theme.** `site.css` describes layout and
relationships. Anything that is a colour, font or radius belongs in a preset as
a token. A hardcoded `#1a1a1a` in `site.css` is unthemeable by construction.

**Nothing consumer-specific.** If a selector only makes sense against one
consumer's markup, it belongs in that consumer's stylesheet, not here.

**Macros take data, not models.** A macro that reaches for a field only one
consumer has is a macro that breaks the other one. `cards.html` was moved back
to `articles-ai` for exactly this reason.

## Worth saying

- A token used but not declared, or declared by some presets and not others.
- Contrast pairs that fail WCAG AA, removed focus styles, targets under 44px.
- A macro whose markup no longer matches what the consumers' tests assert.
- Dead selectors — hard to spot here, because every caller is in another repo.

## Not worth saying

- Formatting, property order, shorthand preferences.
- Suggesting a preprocessor, a framework, or a build step. This is plain CSS
  served as a file on purpose.
