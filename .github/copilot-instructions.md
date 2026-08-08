# Instructions for Copilot in this repository

Read `.github/review-guidelines.md`. It is the specification for what a review
here is looking for, and it is deliberately the same file the weekly
audit reads.

One standard, however many reviewers. Two reviewers with different standards
produce two comments that disagree, and the reader learns to skip both.

## In short

**Defend the invariants.** They are listed in the guidelines file. A change that
weakens one is the finding, whatever else is in the diff.

**Review the change, not the codebase.** Something already wrong before this pull
request is not this pull request's finding.

**Verify before reporting.** A diff hunk does not show whether the guard you
think is missing exists twenty lines above. Findings you could not confirm are
questions, not defects.

**Do not comment on** style, formatting, import order, line length, comment
density, or missing type annotations. This codebase comments *why*, heavily and
on purpose, and matching the surrounding file is the rule. A review that spends
its budget on these misses the one change that mattered.

**Say plainly when you find nothing.** A review that manufactures a finding to
look useful trains the reader to skim.

## One thing specific to this repo

A change here is not shipped when it is merged. It ships when a consumer's pin
moves, which happens in a pull request opened by
`.github/workflows/bump-consumers.yml`. So the blast radius of anything you
approve here is two live sites, and the only tests that will ever exercise it
are in those consumers' repositories.
