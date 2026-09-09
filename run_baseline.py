"""
Runs all 50 cases in golden_dataset.csv through the real n8n agent and logs
each one into LangSmith as a trace tagged run_group="baseline-v1".

Per-case flow: trigger the form -> wait until Draft Brief exists or the run
stops early -> extract all 4 stages' output -> push to LangSmith. Does NOT
wait for Gmail approval (see wait_for_draft_or_finish in harness.py) -- no
emails to click during this run.

Resilient to per-case failure: if one case errors (timeout, n8n hiccup,
etc.), it's recorded and the script moves on to the next case rather than
aborting the whole batch. A local results CSV is written alongside so we
have a paper trail of trace IDs / execution IDs / success flags for Phase 2
failure-clustering, independent of what LangSmith shows.

Run this in a real terminal (needs network). Expect this to take a while --
50 real agent runs, each involving a discovery search + 3x gather + 3x
extract + 1 draft LLM/tool call chain. Safe to Ctrl+C and resume later by
editing RESUME_FROM_CASE_ID below (or just re-running -- LangSmith traces
are additive, re-running a case just adds another trace for it, which is
fine to prune later, but re-running wastes real API credits, so prefer
resuming rather than restarting from scratch after an interruption).
"""

import csv
import sys
import time
import traceback

from harness import (
    trigger_n8n_run,
    wait_for_draft_or_finish,
    extract_node_runs,
    log_case_to_langsmith,
)

RUN_GROUP = "post-improvement-v1"
DATASET_CSV = "golden_dataset.csv"
RESULTS_CSV = "post_improvement_results.csv"
RESUME_FROM_CASE_ID = None  # set to e.g. "hp14" to skip everything before it


def load_cases():
    with open(DATASET_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_case(row):
    case_id = row["case_id"]
    market = row["target_market"]
    company_description = row["company_description"]
    expected_behavior = row["expected_behavior"]
    scenario_type = row["scenario_type"]

    execution_id = trigger_n8n_run(market, company_description)
    execution = wait_for_draft_or_finish(execution_id)
    stages = extract_node_runs(execution)

    task_completed = "draft" in stages
    final_output = stages.get("draft", {}).get("output")

    trace_id = log_case_to_langsmith(
        case_id=f"{RUN_GROUP}-{case_id}",
        inputs={"market": market, "company_description": company_description},
        stages=stages,
        final_output={"brief": final_output},
        expected={"expected_behavior": expected_behavior},
        extra_metadata={
            "n8n_execution_id": execution_id,
            "run_group": RUN_GROUP,
            "case_id": case_id,
            "scenario_type": scenario_type,
            "task_completed": task_completed,
        },
    )
    return {
        "case_id": case_id,
        "scenario_type": scenario_type,
        "n8n_execution_id": execution_id,
        "langsmith_trace_id": trace_id,
        "task_completed": task_completed,
        "error": "",
    }


def main():
    cases = load_cases()
    if RESUME_FROM_CASE_ID:
        idx = next((i for i, r in enumerate(cases) if r["case_id"] == RESUME_FROM_CASE_ID), None)
        if idx is not None:
            cases = cases[idx:]
            print(f"Resuming from case {RESUME_FROM_CASE_ID} ({len(cases)} cases remaining).")

    results = []
    write_header = True
    with open(RESULTS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = None
        for i, row in enumerate(cases, start=1):
            case_id = row["case_id"]
            print(f"\n[{i}/{len(cases)}] Running case {case_id} ({row['scenario_type']}): {row['target_market'][:70]}...")
            start = time.time()
            try:
                result = run_case(row)
                elapsed = time.time() - start
                status = "OK" if result["task_completed"] else "INCOMPLETE (stopped before Draft Brief)"
                print(f"  -> {status} in {elapsed:.0f}s -- trace {result['langsmith_trace_id']}")
            except Exception as e:
                elapsed = time.time() - start
                print(f"  -> ERROR after {elapsed:.0f}s: {e}")
                traceback.print_exc()
                result = {
                    "case_id": case_id,
                    "scenario_type": row["scenario_type"],
                    "n8n_execution_id": "",
                    "langsmith_trace_id": "",
                    "task_completed": False,
                    "error": str(e),
                }

            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(result.keys()))
                if write_header:
                    writer.writeheader()
            writer.writerow(result)
            f.flush()
            results.append(result)

    completed = sum(1 for r in results if r["task_completed"])
    print(f"\nDone. {completed}/{len(results)} cases reached Draft Brief successfully.")
    print(f"Full results written to {RESULTS_CSV}.")


if __name__ == "__main__":
    main()
