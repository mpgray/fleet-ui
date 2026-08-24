#!/usr/bin/env bash
# Resolve `provider:model` strings into one endpoint plus bare model ids.
#
# Split out of action.yml so it can be run directly:
#
#   AI_BASE_URL=https://ai.example.com \
#   PRIMARY=litellm:qwen3-coder ./resolve.sh
#
# and so the test in tests/ can exercise it without a GitHub runner. A resolver
# living only inside a workflow is one whose edge cases are discovered in
# production, at one push per experiment.
#
# ## One job is one endpoint
#
# ANTHROPIC_BASE_URL is a single value for the whole job, but Claude Code reads
# four model ids from it: the primary plus the opus/sonnet/haiku aliases that
# subagents and background traffic ask for by name. They all go to that one
# endpoint.
#
# So the four must agree on a provider. `litellm:` primary with an `openrouter:`
# alias is not a mixed configuration, it is a broken one: the alias id would be
# sent to LiteLLM, which has never heard of it. This refuses that rather than
# letting it fail forty turns later as a confusing 400.
set -euo pipefail

KNOWN_PROVIDERS='litellm openrouter'
OPENROUTER_BASE='https://openrouter.ai/api'

# split "<provider>:<model>" -> sets SPLIT_PROVIDER / SPLIT_MODEL
#
# Only a KNOWN provider counts as a prefix. This mirrors parse_model_override()
# in app/ai/clients.py deliberately: an OpenRouter id can itself contain a colon
# ('qwen2.5:14b'), so splitting on the first colon unconditionally would mangle
# a perfectly good model id into a bogus provider.
split_model() {
  local value="${1:-}" head tail p
  SPLIT_PROVIDER='' SPLIT_MODEL="$value"
  [ -z "$value" ] && { SPLIT_MODEL=''; return 0; }
  case "$value" in *:*) ;; *) return 0 ;; esac
  head="${value%%:*}"
  tail="${value#*:}"
  [ -n "$tail" ] || return 0
  for p in $KNOWN_PROVIDERS; do
    if [ "$head" = "$p" ]; then
      SPLIT_PROVIDER="$p"
      SPLIT_MODEL="$tail"
      return 0
    fi
  done
  return 0
}

die() { echo "::error::$*" >&2; exit 1; }

PRIMARY="${PRIMARY:-}"
OPUS="${OPUS:-}"
SONNET="${SONNET:-}"
HAIKU="${HAIKU:-}"
AI_BASE_URL="${AI_BASE_URL:-}"

[ -n "$PRIMARY" ] || die "no primary model given — the MODEL_* variable for this job is empty and its workflow default did not apply"

# ── Agree on one provider, or refuse ─────────────────────────────────────
PROVIDER=''
NAMED_BY=''
for pair in "primary=$PRIMARY" "opus=$OPUS" "sonnet=$SONNET" "haiku=$HAIKU"; do
  role="${pair%%=*}"; value="${pair#*=}"
  [ -n "$value" ] || continue
  split_model "$value"
  [ -n "$SPLIT_PROVIDER" ] || continue
  if [ -z "$PROVIDER" ]; then
    PROVIDER="$SPLIT_PROVIDER"; NAMED_BY="$role"
  elif [ "$PROVIDER" != "$SPLIT_PROVIDER" ]; then
    die "this job names two providers: $NAMED_BY says '$PROVIDER' and $role says '$SPLIT_PROVIDER'. ANTHROPIC_BASE_URL is one value for the whole job, so every model it uses — including the opus/sonnet/haiku aliases — must be served by the same endpoint."
  fi
done

# ── Pick the endpoint ────────────────────────────────────────────────────
case "$PROVIDER" in
  openrouter)
    BASE="$OPENROUTER_BASE" ;;
  litellm)
    [ -n "$AI_BASE_URL" ] \
      || die "a model names 'litellm:' but the AI_BASE_URL repository variable is empty. Set it to the proxy's origin (no trailing /v1), or use an 'openrouter:' prefix."
    BASE="$AI_BASE_URL" ;;
  '')
    # Unprefixed. Exactly the behaviour before this action existed: whatever
    # AI_BASE_URL says, falling back to OpenRouter. Every currently-configured
    # MODEL_* value in the fleet is unprefixed, so this is the path they take
    # and nothing changes for them on the day this merges.
    BASE="${AI_BASE_URL:-$OPENROUTER_BASE}" ;;
esac

# Trailing slash off: ai-preflight appends /v1/messages, and "//v1" 404s on
# some gateways while working on others — which is the kind of difference that
# gets diagnosed as a credential problem.
BASE="${BASE%/}"

emit() { if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1=$2" >> "$GITHUB_OUTPUT"; else echo "$1=$2"; fi; }

split_model "$PRIMARY"; emit model  "$SPLIT_MODEL"
split_model "$OPUS";    emit opus   "$SPLIT_MODEL"
split_model "$SONNET";  emit sonnet "$SPLIT_MODEL"
split_model "$HAIKU";   emit haiku  "$SPLIT_MODEL"
emit provider "$PROVIDER"
emit base_url "$BASE"

echo "resolved: provider=${PROVIDER:-<unprefixed>} endpoint=$BASE"
