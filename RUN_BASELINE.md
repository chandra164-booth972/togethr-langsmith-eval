# Phase 1 baseline run -- run this in a real Terminal window on your Mac

Same reason as before: this needs live internet access, which only your real
Terminal has (Claude's own sandboxes are network-restricted by policy).

## What this does

Runs all 50 cases in `golden_dataset.csv` through your real n8n agent,
sequentially. For each case it:
1. Triggers the production form with that case's market + company description.
2. Polls until either the **Draft Brief** node has output, or the execution
   stops/finishes early. It does **NOT** wait for the Gmail approval step --
   per your call, we're scoring everything up through Draft Brief and skipping
   the human-in-the-loop gate for eval purposes.
3. Pulls all 4 stages' input/output out of the execution record.
4. Pushes it into LangSmith as a trace tagged `run_group=baseline-v1`.
5. Appends a row to `baseline_results.csv` (case_id, execution_id, trace_id,
   task_completed, error) so we have a local paper trail independent of
   LangSmith, for failure-clustering later.

**No emails to approve this run** -- that's the whole point of the
`wait_for_draft_or_finish` change from last session.

## Before you run it

Make sure you're using the same venv/`.env` as before:

```bash
cd ~/Documents/togethr-langsmith-eval
source venv/bin/activate
```

Quick sanity check that everything's current:

```bash
ls harness.py run_baseline.py golden_dataset.csv
```

All three should exist in that folder.

## Run it

```bash
python3 run_baseline.py
```

## What to expect

- It prints one line per case as it goes, e.g.:
  `[1/50] Running case hp01 (happy_path): Relationship coaching...`
  `  -> OK in 143s -- trace <uuid>`
- **This will take a while.** 50 real agent runs, each with a discovery
  search + 3x gather + 3x extract + 1 draft LLM/tool chain. Budget at least
  1.5-2+ hours depending on n8n/LLM latency -- do not expect this to be fast,
  and don't worry if a single case takes several minutes.
- If a case errors out (timeout, n8n hiccup, rate limit, etc.), it's caught,
  logged as a failure in `baseline_results.csv`, and the script moves on to
  the next case automatically -- it won't crash the whole batch.
- It's safe to Ctrl+C and resume later: open `run_baseline.py`, set
  `RESUME_FROM_CASE_ID = "hp14"` (or whatever the next un-run case is, check
  `baseline_results.csv` for the last completed one), and re-run. Don't just
  blindly re-run the whole thing from scratch -- that wastes real API credits
  re-doing cases you already have.
- At the end it prints a summary: `Done. X/50 cases reached Draft Brief
  successfully.`

## Keep an eye on n8n Cloud execution quota

You're on the Starter plan (2,500 executions/month). This run alone uses up
to 50 executions -- worth a glance at n8n Cloud's usage page afterward,
especially since Phase 3's post-improvement run will use ~50 more.

## After it finishes

1. Send me `baseline_results.csv` (or paste its contents) so we can see the
   completion rate and start Phase 2 (failure clustering + evaluators).
2. Optionally, spot-check 2-3 traces in LangSmith under
   `togethr-market-research-eval`, filtered/grouped by `run_group=baseline-v1`,
   to eyeball that the Draft Brief output looks reasonable across a happy-path,
   an edge-case, and a known-failure case.

## If it errors in a way that isn't a per-case failure (script itself crashes)

Paste me the full terminal output / traceback and I'll debug from there.
