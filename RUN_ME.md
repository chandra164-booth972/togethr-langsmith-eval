# Phase 0 smoke test -- run this in a real Terminal window on your Mac

This has to run in Terminal.app (or iTerm) directly -- not through any Claude
tool -- because this folder's normal internet access is what we need, and
Claude's own sandboxes are network-restricted by policy.

## One-time setup

```bash
cd ~/Documents/togethr-langsmith-eval
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run the smoke test

```bash
python3 harness.py
```

What happens: it triggers your real n8n production form with one real market
("Relationship coaching, counseling, and therapy in India"), polls n8n until
the execution finishes, and pushes one trace with four child runs into your
`togethr-market-research-eval` LangSmith project.

**Important:** this is a REAL run. It spends real OpenAI/you.com credits,
sends a real Gmail approval email, and (if you approve it) creates a real
Google Doc + Sheets row. Approve that Gmail email promptly once it arrives --
per your own Week 3 debugging notes, a long delay before approving is what
triggered the "Loop Over Items silently stops" bug on execution #91.

## What to check afterward

1. Terminal should print something like:
   `Case phase0-smoke-test: n8n execution <id> -> LangSmith trace <id>`
2. Open LangSmith -> Tracing -> togethr-market-research-eval and confirm you
   see one new trace named `case-phase0-smoke-test` with 4 child runs
   (Discovery, Gather, Extract, Draft Brief) underneath it, each showing
   input/output and duration.

## If it errors

- If you see a `[warn] Could not find these configured node names...` line,
  it printed the actual node names from your workflow -- copy those back to
  me and I'll fix `NODE_NAMES` at the top of `harness.py`.
- Paste me the full terminal output (or a screenshot) for anything else and
  I'll debug from there.
