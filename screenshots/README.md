# Screenshots to add here

This folder holds the visual evidence for the LangSmith deliverable. Add these (PNG or JPG), named as listed, then reference them from the main README:

1. `langsmith-project-overview.png` -- the `togethr-market-research-eval` project's trace list in LangSmith, ideally sorted/filtered so both the baseline run (Sept 7, 2026, n8n executions 153-202) and the post-improvement run (Sept 8, 2026, n8n executions 205-254) are visible. Note: both runs share the same `run_group`/`case_id` metadata due to a config-timing bug documented in the solution doc (Phase 3.5) -- distinguish them by date or execution ID, not by a metadata filter.
2. `langsmith-trace-expanded.png` -- a single expanded trace showing the 4 child stages (Discovery / Gather / Extract / Draft).
3. `langsmith-dataset-view.png` -- the `togethr-market-research-golden-v1` dataset (50 examples) in the LangSmith Datasets tab.
4. `langsmith-feedback-scores.png` (optional but nice) -- a trace showing the attached evaluator feedback scores (structural_completeness, citation_presence, faithfulness, competitor_relevance) from `score_baseline.py` / `score_post_improvement.py`.
