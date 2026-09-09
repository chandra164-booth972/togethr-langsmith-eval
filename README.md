# Togethr Market Research Agent -- LangSmith Evaluation (Week 4, Track 3)

Evaluating my own Week 3 n8n Market Research / Competitor Analysis agent for Togethr using LangSmith: baseline run, root-cause diagnosis, two targeted fixes, and a re-scored post-improvement run.

**Full writeup:** [`togethr_agent_evaluation_solution.docx`](./togethr_agent_evaluation_solution.docx) (or the [`.md` version](./togethr_agent_evaluation_solution.md)) -- start there for the complete framework, results, and findings.

## Results at a glance

| Metric | Baseline (40 cases) | Post-improvement (50 cases) | Bar |
|---|---|---|---|
| Task completion | 80% | **100%** | 90% |
| Structural completeness | 100% | 100% | 100% |
| Citation presence | 85% | 60%* | 90% |
| Faithfulness | 68% | 60%* | 90% |
| Competitor relevance | 92% | 82%* | 85% |

\* Not an agent regression -- see the solution doc's Section 7. Both fixes were validated by directly reading real brief output; the drop is a documented evaluator design gap (the code-based citation check can't distinguish an honest "no public data exists" disclosure from a sloppy one), not a fabrication regression.

## LangSmith

- Project: `togethr-market-research-eval`
- Golden dataset: `togethr-market-research-golden-v1` (50 examples, id `d7be8dd2-916c-4e4e-8d61-81801756056e`)
- Baseline traces: n8n executions 153-202 (Sept 7, 2026)
- Post-improvement traces: n8n executions 205-254 (Sept 8, 2026)
- Screenshots: see [`screenshots/`](./screenshots)

## Repo layout

| File | What it does |
|---|---|
| `build_dataset.py` | Generates `golden_dataset.csv` (50 cases, scenario-mix distribution) |
| `upload_dataset.py` | Uploads the golden dataset into LangSmith as a versioned dataset |
| `harness.py` | Core harness: triggers the n8n form, polls for the finished execution, extracts per-stage output, logs traces to LangSmith |
| `run_baseline.py` | Runs all 50 cases through the harness for a given run (baseline or post-improvement, via `RUN_GROUP`/`RESULTS_CSV` config at the top of the file) |
| `evaluators.py` | Code-based evaluators: structural completeness, citation presence |
| `llm_judges.py` | LLM-as-judge evaluators: faithfulness, competitor relevance |
| `score_baseline.py` / `score_post_improvement.py` | Score a completed run's results CSV against all 4 metrics, write `evaluation_scores*.csv`, attach LangSmith feedback |
| `diagnose_failures.py` | Pulls raw execution data for non-completing cases to find the real failure mechanism |
| `dump_sample_brief.py` | Fetches a single execution's Draft Brief text for manual reading (used throughout for root-causing, never guessing) |
| `replay_case.py` | Re-processes an already-completed n8n execution into LangSmith (does not trigger a new run) |
| `golden_dataset.csv` | The 50-case dataset (25 happy path / 15 edge case / 8 known failure / 2 adversarial) |
| `baseline_results.csv` / `post_improvement_results.csv` | Per-case execution/trace IDs and completion status for each run |
| `evaluation_scores.csv` / `evaluation_scores_post_improvement.csv` | Per-case scores against all 4 metrics for each run |
| `sample_brief_*.txt` | Real brief text pulled during root-cause diagnosis and fix validation -- referenced directly in the solution doc |

## Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your own LANGSMITH_API_KEY / OPENAI_API_KEY
```

## The two fixes (n8n workflow, not in this repo -- see solution doc for details)

1. **Agent 1 reliability:** Max Iterations 10 -> 20, plus graceful degradation in the "Split Competitors" code node (an honest placeholder instead of a hard crash) when Agent 1 still can't converge.
2. **Citation discipline:** a stronger, more explicit citation instruction in the "Orchestrator - Draft Brief" prompt, banning fabricated empty-href citations and requiring explicit "no public source found" language instead.

Both were validated against real, directly-read agent output, not evaluator scores alone -- including a deliberately forced-failure test for fix 1 (Max Iterations dropped to 1 to guarantee a convergence failure, confirming the pipeline still completes and produces an honest brief).
