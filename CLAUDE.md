# CLAUDE.md

Project instructions for Claude Code when working in this repo.

## Always on

- **Ponytail, every response.** Simplest solution that works: stdlib and
  already-installed system tools before new dependencies, no speculative
  abstractions, shortest correct diff. Don't wait to be reminded.
- **Senior code structure.** One module = one responsibility (a backend, the
  scanner, the risk classifier, the GUI are separate files). Pure logic
  (parsing, classification) stays free of subprocess/IO calls so it's testable
  without a live system. No dead code, no scaffolding for features nobody
  asked for.

## Before touching a feature

1. Read [documents/ai-knowledgebase.md](documents/ai-knowledgebase.md) — how the
   pieces fit together, decisions already made, and why.
2. Read [documents/features.md](documents/features.md) — what exists, what's
   planned, what's explicitly out of scope.
3. Only then write code.

## After shipping a feature

Update **both** files above in the same change:
- `ai-knowledgebase.md`: the design decision, the tradeoff, anything a future
  session needs to not re-litigate it.
- `features.md`: move the item to Done (or add it) with a one-line
  description.

Treat these two files as part of the diff, not follow-up busywork.

## Reference docs

- [documents/SRS.md](documents/SRS.md) — Software Requirements Specification
  (source of truth; export to PDF with `pandoc documents/SRS.md -o documents/SRS.pdf`
  if a PDF copy is needed — see README).

## Non-negotiables (ponytail's own exceptions)

Never simplify away: destructive-action confirmation before an uninstall or
leftover deletion, privilege-escalation prompts (pkexec) for anything
touching system packages, and the risk label shown to the user. These are
safety rails on a tool that deletes software — they stay even when a leaner
diff is tempting.
