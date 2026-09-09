"""
Togethr Market Research Agent -- LangSmith eval harness (skeleton)

What this does, end to end, for ONE golden-dataset case:
  1. Trigger the n8n workflow's webhook with {market, company_description}.
  2. Poll the n8n REST API for that execution until it finishes.
  3. Pull each node's input/output data out of the execution record.
  4. Push it into LangSmith as ONE parent trace (the case) with FOUR child
     runs (Discovery, Gather, Extract, Draft), tagged with the metadata the
     Week 4 handout asks for: case ID, run name, prompt version, expected
     vs. predicted output, correctness, tokens, latency.

Nothing in here executes automatically -- Phase 0 is just getting run_one_case()
to work end-to-end for a single real case and confirming the trace shows up
correctly shaped in LangSmith before we touch the 50-case dataset.

Fill in the constants below (or set them as env vars) once the n8n hosting
decision is made and the LangSmith project/API key exist.
"""

import os
import time
import json
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from langsmith import Client as LangSmithClient
from langsmith.run_trees import RunTree

load_dotenv()  # reads .env in the same folder as this script

# ---------------------------------------------------------------------------
# Config -- set these as environment variables rather than hardcoding secrets.
# ---------------------------------------------------------------------------
N8N_BASE_URL = os.environ.get("N8N_BASE_URL", "")          # e.g. https://togethrapp.app.n8n.cloud  OR  https://<ngrok-id>.ngrok-free.app
N8N_WEBHOOK_PATH = os.environ.get("N8N_WEBHOOK_PATH", "")  # production webhook path from the Form/Webhook trigger node
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")            # Settings -> n8n API -> Create an API key
N8N_WORKFLOW_ID = os.environ.get("N8N_WORKFLOW_ID", "8OXerbGsoUyXPdxn")  # from your workflow URL

LANGSMITH_API_KEY = os.environ.get("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.environ.get("LANGSMITH_PROJECT", "togethr-market-research-eval")
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "baseline-v1")  # bump this string after Phase 3 changes
EVAL_FLAG_VALUE = os.environ.get("EVAL_FLAG_VALUE", "eval-skip")  # sent as field-2 -- tells the n8n workflow's
                                                                   # "If Eval Run" node to skip Gmail approval +
                                                                   # doc/sheet write and end right after Draft Brief.

# Node names as they appear in the n8n canvas -- adjust to match exactly
# (visible in the Executions tab / execution JSON "resultData.runData" keys).
NODE_NAMES = {
    "discovery": "Agent 1 - Discover Competitors",  # confirmed from execution #99
    "gather": "Agent 2 - Gather Data",              # confirmed from execution #99
    "extract": "Agent 3 - Extract Structured Data", # confirmed from execution #99
    "draft": "Orchestrator - Draft Brief",          # confirmed from execution #99
}

ls_client = LangSmithClient(api_key=LANGSMITH_API_KEY) if LANGSMITH_API_KEY else None


# ---------------------------------------------------------------------------
# Step 1: trigger the workflow
# ---------------------------------------------------------------------------
def trigger_n8n_run(market: str, company_description: str) -> str:
    """
    Calls the production Form Trigger and returns n8n's execution ID.

    n8n Form Trigger nodes expect a multipart/form-data POST keyed by the
    EXACT field labels defined on the form -- not arbitrary JSON keys. For
    this workflow ("Form: Start Research") those labels are:
        "Company Description"  (textarea)
        "Target Market"
    (confirmed via GET /api/v1/workflows/<id> and inspecting the formTrigger
    node's parameters -- if you ever redesign the form, re-check this.)

    Confirmed by hand: `curl -F "Company Description=..." -F "Target Market=..."`
    against this same URL returns HTTP 200. Python's `requests` `files=` trick
    (None-filename multipart) did NOT get accepted by n8n's parser for reasons
    not worth chasing under time pressure -- so this shells out to curl
    directly instead, matching the exact request shape already proven to work.

    NOTE: n8n's Form/Webhook trigger response does not always include the
    execution ID directly. If it doesn't, fall back to GET /executions
    filtered by workflowId + startedAfter=<timestamp we recorded just before
    the call> and take the most recent one.
    """
    import subprocess

    url = f"{N8N_BASE_URL}/{N8N_WEBHOOK_PATH.lstrip('/')}"
    started_at = datetime.now(timezone.utc).isoformat()

    result = subprocess.run(
        [
            "curl", "-s", "-w", "\n%{http_code}",
            "-X", "POST", url,
            # Confirmed via real browser DevTools Network tab: n8n's Form
            # Trigger submits generic "field-N" keys (N = declaration order),
            # NOT the field labels. field-0 = Company Description,
            # field-1 = Target Market, per this form's field order.
            "-F", f"field-0={company_description}",
            "-F", f"field-1={market}",
            # field-2 = the "QA Flag" field added to the form -- triggers the
            # workflow's "If Eval Run" IF node to skip Gmail approval and the
            # doc/sheet write, so eval executions finish in seconds instead of
            # hanging indefinitely on a human approval that will never come.
            "-F", f"field-2={EVAL_FLAG_VALUE}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    *body_lines, status_code = result.stdout.rsplit("\n", 1)
    body = "\n".join(body_lines)
    if not status_code.strip().startswith("2"):
        raise RuntimeError(f"curl POST failed: HTTP {status_code}\n{body}\nstderr: {result.stderr}")

    # A Form Trigger's production response is usually an HTML "thanks" page,
    # not JSON with an executionId -- so we normally go straight to the
    # fallback lookup. Only try to parse JSON if it looks like JSON.
    execution_id = None
    if body.strip().startswith("{"):
        try:
            execution_id = json.loads(body).get("executionId")
        except ValueError:
            pass
    if execution_id:
        return execution_id

    # Fallback: look up the most recent execution for this workflow started
    # at/after `started_at`.
    return _find_execution_by_time(started_at)


def _find_execution_by_time(started_after_iso: str, retries: int = 150, retry_delay_s: float = 4.0) -> str:
    """
    Looks up the execution we just triggered by matching startedAt against the
    timestamp recorded right before the curl POST -- retrying with a short
    delay, because n8n sometimes hasn't registered the new execution in the
    list API yet by the time we ask.

    This replaces the old "just take the newest of the last 5" approach,
    which (confirmed from real baseline-v1 run data) silently attributed
    several consecutive cases to the SAME stale execution ID when new
    executions were slow to register -- back when approval-gated executions
    could sit "waiting" for minutes, piling up against n8n Cloud's 5-concurrent
    limit and starving new ones. Now that eval runs skip the approval wait
    entirely (see EVAL_FLAG_VALUE / "If Eval Run" node), executions finish in
    seconds and this race window is much smaller -- but we still guard it
    properly instead of hoping.
    """
    started_after = datetime.fromisoformat(started_after_iso)
    for attempt in range(retries):
        resp = requests.get(
            f"{N8N_BASE_URL}/api/v1/executions",
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            params={"workflowId": N8N_WORKFLOW_ID, "limit": 5},
            timeout=30,
        )
        resp.raise_for_status()
        executions = resp.json().get("data", [])
        for execution in executions:
            started_at_raw = execution.get("startedAt")
            if not started_at_raw:
                continue
            started_at = datetime.fromisoformat(started_at_raw.replace("Z", "+00:00"))
            if started_at >= started_after:
                return str(execution["id"])
        time.sleep(retry_delay_s)
    raise RuntimeError(
        f"Could not find an execution that started at/after {started_after_iso} "
        f"after {retries} retries (~{retries * retry_delay_s:.0f}s) -- did the webhook actually fire?"
    )


# ---------------------------------------------------------------------------
# Step 2: poll until finished
# ---------------------------------------------------------------------------
def wait_for_execution(execution_id: str, timeout_s: int = 900, poll_every_s: int = 5) -> dict:
    """
    Polls GET /api/v1/executions/{id}?includeData=true until `finished` is
    true (or `stoppedAt` is set), then returns the full execution JSON.

    900s (15 min) default timeout matches the agent's own target runtime --
    if a case blows past this, that's itself a task-completion failure worth
    recording, not just a harness bug.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = requests.get(
            f"{N8N_BASE_URL}/api/v1/executions/{execution_id}",
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            params={"includeData": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        execution = resp.json()
        if execution.get("finished") or execution.get("stoppedAt"):
            return execution
        time.sleep(poll_every_s)
    raise TimeoutError(f"Execution {execution_id} did not finish within {timeout_s}s")


def wait_for_draft_or_finish(execution_id: str, timeout_s: int = 900, poll_every_s: int = 5) -> dict:
    """
    Eval-mode wait: polls until EITHER
      (a) the Orchestrator - Draft Brief node has produced output -- this is
          everything we need to score a case (faithfulness, structure,
          competitor relevance), since the brief itself is fully formed by
          this point -- or
      (b) the execution has stopped/errored before ever reaching Draft Brief
          (a real task-completion failure worth recording).

    Deliberately does NOT wait for the human Gmail approval step or the
    subsequent Google Docs/Sheets write-back that follows it -- those are
    business/delivery mechanics, not part of what makes the research good or
    bad, and waiting for a human click on up to 100 eval runs (50 baseline +
    50 post-improvement) isn't viable. The execution is left sitting in
    n8n's "Waiting" state indefinitely after this returns -- harmless, no
    further API/credit cost, and needs no action from Abhi.
    """
    deadline = time.time() + timeout_s
    draft_node = NODE_NAMES["draft"]
    while time.time() < deadline:
        resp = requests.get(
            f"{N8N_BASE_URL}/api/v1/executions/{execution_id}",
            headers={"X-N8N-API-KEY": N8N_API_KEY},
            params={"includeData": "true"},
            timeout=30,
        )
        resp.raise_for_status()
        execution = resp.json()
        run_data = execution.get("data", {}).get("resultData", {}).get("runData", {})
        if draft_node in run_data:
            return execution
        if execution.get("finished") or execution.get("stoppedAt"):
            # Execution ended (errored, or trivially completed) without ever
            # reaching Draft Brief -- a real task-completion failure.
            return execution
        time.sleep(poll_every_s)
    raise TimeoutError(f"Execution {execution_id} did not reach Draft Brief or stop within {timeout_s}s")


# ---------------------------------------------------------------------------
# Step 3: pull per-node data out of the execution record
# ---------------------------------------------------------------------------
def extract_node_runs(execution: dict) -> dict:
    """
    n8n execution JSON shape (community/cloud, roughly):
        execution["data"]["resultData"]["runData"][<node name>] -> list of
        run attempts, each with .data.main[0][0].json (output) and
        .startTime / .executionTime (ms).

    Returns {stage_key: {"input":..., "output":..., "start_time":..., "duration_ms":...}}
    for the four stages in NODE_NAMES. Missing nodes (e.g. run aborted early)
    are simply omitted -- that's a real signal for task-completion scoring.
    """
    run_data = execution.get("data", {}).get("resultData", {}).get("runData", {})
    stages = {}
    missing = []
    for stage_key, node_name in NODE_NAMES.items():
        attempts = run_data.get(node_name)
        if not attempts:
            missing.append(node_name)
            continue
        last = attempts[-1]  # last attempt if there were retries
        out_items = last.get("data", {}).get("main", [[]])[0]
        stages[stage_key] = {
            "output": [item.get("json") for item in out_items] if out_items else None,
            "start_time": last.get("startTime"),
            "duration_ms": last.get("executionTime"),
            "error": last.get("error"),
        }
    if missing:
        actual_nodes = list(run_data.keys())
        print(
            f"[warn] Could not find these configured node names in the execution: {missing}\n"
            f"       Actual node names in this execution were: {actual_nodes}\n"
            f"       Update NODE_NAMES at the top of this file to match, then re-run."
        )
    return stages


# ---------------------------------------------------------------------------
# Step 4: push a full case trace into LangSmith
# ---------------------------------------------------------------------------
def log_case_to_langsmith(
    case_id: str,
    inputs: dict,
    stages: dict,
    final_output: dict,
    expected: dict | None = None,
    extra_metadata: dict | None = None,
):
    """
    Builds ONE parent run (the case) with one child run per agent stage.
    correctness/scores are attached later by the evaluator step (Phase 2) --
    this function's job is just to get inputs/outputs/timing/metadata into
    LangSmith in a stable, comparable shape for baseline vs. post-improvement.
    """
    if ls_client is None:
        raise RuntimeError("LANGSMITH_API_KEY not set")

    common_metadata = {
        "case_id": case_id,
        "prompt_version": PROMPT_VERSION,
        "expected_output": expected,
        **(extra_metadata or {}),
    }

    parent = RunTree(
        name=f"case-{case_id}",
        run_type="chain",
        inputs=inputs,
        project_name=LANGSMITH_PROJECT,
        extra={"metadata": common_metadata},
    )
    parent.post()

    for stage_key, stage_data in stages.items():
        if stage_data is None:
            continue
        child = parent.create_child(
            name=NODE_NAMES.get(stage_key, stage_key),
            run_type="chain",
            inputs=inputs if stage_key == "discovery" else {},  # refine once real payloads are seen
            extra={
                "metadata": {
                    **common_metadata,
                    "stage": stage_key,
                    "duration_ms": stage_data.get("duration_ms"),
                }
            },
        )
        child.post()
        child.end(
            outputs={"result": stage_data.get("output")},
            error=stage_data.get("error"),
        )
        child.patch()

    parent.end(outputs=final_output)
    parent.patch()
    return parent.id


# ---------------------------------------------------------------------------
# Orchestration for one case -- this is what Phase 0 needs to prove out.
# ---------------------------------------------------------------------------
def run_one_case(case_id: str, market: str, company_description: str, expected: dict | None = None) -> str:
    execution_id = trigger_n8n_run(market, company_description)
    execution = wait_for_execution(execution_id)
    stages = extract_node_runs(execution)
    final_output = stages.get("draft", {}).get("output")
    trace_id = log_case_to_langsmith(
        case_id=case_id,
        inputs={"market": market, "company_description": company_description},
        stages=stages,
        final_output={"brief": final_output},
        expected=expected,
        extra_metadata={"n8n_execution_id": execution_id},
    )
    print(f"Case {case_id}: n8n execution {execution_id} -> LangSmith trace {trace_id}")
    return trace_id


if __name__ == "__main__":
    # Phase 0 smoke test -- run exactly one real case and stop.
    #
    # HEADS UP: this triggers the REAL production workflow. It will spend
    # real OpenAI/you.com API credits, send a REAL Gmail approval email, and
    # (if approved) create a real Google Doc + Sheets row. Per your own
    # Week 3 notes, approve that email PROMPTLY once it lands -- a long pause
    # before approving is the exact condition that triggered the "Loop Over
    # Items silently stops" bug on a past run.
    print(">>> This will trigger a REAL n8n run. Check your inbox and approve the Gmail request promptly. <<<")
    run_one_case(
        case_id="phase0-smoke-test",
        market="Relationship coaching, counseling, and therapy in India",
        company_description="Togethr: a relationship-navigation platform for singles, couples, and families.",
    )
