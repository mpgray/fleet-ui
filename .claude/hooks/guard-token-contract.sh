#!/usr/bin/env bash
# PreToolUse hook: refuse an edit that would leave a theme preset missing one of
# the 12 required CSS custom properties in the token contract.
#
# site.css declares zero literal colors, fonts, or radii — every one comes from
# a theme file defining these tokens (see README.md, "The token contract").
# Dropping one during an edit does not fail anything here; the affected
# property renders as nothing on every site using that preset, and CI's
# check_contrast.py only catches it if the missing token happens to be one it
# samples for contrast. This catches a dropped token at edit time, for any
# token, contrast-relevant or not.
#
# Reads the PreToolUse payload on stdin; denies by returning permissionDecision.
set -euo pipefail

REQUIRED_TOKENS="--bg --surface --text --muted --accent --accent-contrast --border --font-body --font-heading --radius --header-bg --header-text"

payload="$(cat)"
tool="$(printf '%s' "$payload" | jq -r '.tool_name // empty')"
path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')"

[ -n "$path" ] || exit 0
case "$path" in
  */css/themes/*.css|css/themes/*.css) ;;
  *) exit 0 ;;
esac

deny() {
  jq -n --arg r "$1" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $r
    }
  }'
  exit 0
}

# Reconstruct what the file will contain after the edit, so the check runs on
# the result rather than on just the changed fragment.
case "$tool" in
  Write)
    content="$(printf '%s' "$payload" | jq -r '.tool_input.content // empty')"
    ;;
  Edit)
    [ -f "$path" ] || exit 0
    old="$(printf '%s' "$payload" | jq -r '.tool_input.old_string // empty')"
    new="$(printf '%s' "$payload" | jq -r '.tool_input.new_string // empty')"
    content="$(python3 - "$path" "$old" "$new" <<'PYEOF'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
data = open(path).read()
if data.count(old) != 1:
    # Ambiguous or not found — let the Edit tool itself handle that failure.
    sys.exit(0)
sys.stdout.write(data.replace(old, new, 1))
PYEOF
)"
    ;;
  *) exit 0 ;;
esac

[ -n "$content" ] || exit 0

missing=""
for token in $REQUIRED_TOKENS; do
  printf '%s' "$content" | grep -qF -- "$token:" || missing="$missing $token"
done

[ -n "$missing" ] || exit 0

deny "This edit would leave $(basename "$path") missing:$missing

The token contract requires all twelve custom properties in every theme file
(README.md, \"The token contract\"). A missing token doesn't fail here — the
property it backs renders as nothing on every site using this preset, silently.
If you're removing a token deliberately, that's a breaking change for every
consumer (articles-ai, game-db, ai-help, toolbox) and belongs in a reviewable
diff that updates the contract in README.md too, not a quiet drop in one file."
