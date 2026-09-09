# Screenshots

Visual evidence for the LangSmith / dataset deliverable.

- `langsmith-trace-feedback-scores.png` -- a single expanded trace (`case-baseline-v1-adv01`) showing the 4 child agent stages (Discover Competitors / Gather Data / Extract Structured Data / Draft Brief) and, in the Feedback tab, all 4 real evaluator scores attached to that case: `citation_presence 1.00`, `competitor_relevance 1.00`, `faithfulness 0.80`, `structural_completeness 1.00`. This is the strongest piece of evidence here -- it shows the evaluators actually ran against real agent output and posted scores back to LangSmith, not just that tracing happened.
- `langsmith-trace-list-citation-scores.png` -- the project's trace list with the Feedback column visible, showing `citation_presence` scores across many real cases at a glance.
- `golden-dataset-view.png` -- the 50-case `golden_dataset.csv` open in a spreadsheet, showing the `case_id` / `scenario_type` / `target_market` / `company_description` / `expected_behavior` columns and the scenario-mix distribution (happy_path / edge_case / known_failure / adversarial) described in the solution doc.

**Note on the trace list's Latency column:** those near-instant times (0.00s-0.02s) are how long it took to POST the already-finished trace to LangSmith's API after the fact, not real agent runtime. Each actual n8n agent run took roughly 70-100 seconds (discovery search + 3x gather + 3x extract + draft). Don't read the Latency column as agent performance.

**Note on run identification:** baseline and post-improvement traces share the same `case-baseline-v1-*` naming and metadata due to a config-timing bug documented in the solution doc (Phase 3.5) -- a `run_baseline.py` config edit landed after that run had already started, so both runs are tagged identically. They're distinguishable only by date (baseline: Sept 7, 2026; post-improvement: Sept 8, 2026) and by n8n execution ID (baseline: 153-202; post-improvement: 205-254), not by any LangSmith filter.
