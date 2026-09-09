"""
Uploads golden_dataset.csv into LangSmith as a versioned dataset.

Per the Week 4 handout: "Store as a LangSmith dataset, not a CSV" and
"Version your dataset. Tag the dataset version used for baseline and
re-evaluation." This script creates the dataset once (idempotent -- safe to
re-run, it reuses the dataset if it already exists) and tags this exact
upload as a dataset version so the baseline run and the post-improvement
run can both point at the same frozen set of examples.

Run this in a real terminal (needs network) -- NOT via any Claude-controlled
shell, which is network-restricted by policy.
"""

import csv
import os
from dotenv import load_dotenv
from langsmith import Client

load_dotenv()

DATASET_NAME = "togethr-market-research-golden-v1"
DATASET_DESCRIPTION = (
    "Week 4 golden dataset for evaluating the Togethr Market Research / "
    "Competitor Analysis agent (n8n). 50 cases: 25 happy path, 15 edge case, "
    "8 known failure (India-focused), 2 adversarial."
)
VERSION_TAG = "v1-2026-09-07"

client = Client(api_key=os.environ["LANGSMITH_API_KEY"])


def get_or_create_dataset():
    for ds in client.list_datasets(dataset_name=DATASET_NAME):
        print(f"Dataset '{DATASET_NAME}' already exists (id={ds.id}) -- reusing it.")
        return ds
    ds = client.create_dataset(dataset_name=DATASET_NAME, description=DATASET_DESCRIPTION)
    print(f"Created dataset '{DATASET_NAME}' (id={ds.id}).")
    return ds


def load_rows(path="golden_dataset.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    dataset = get_or_create_dataset()
    rows = load_rows()
    assert len(rows) == 50, f"Expected 50 rows in golden_dataset.csv, found {len(rows)}"

    # Wipe and re-add examples each run so re-running this script after edits
    # gives byte-for-byte reproducible dataset content rather than duplicates.
    existing = list(client.list_examples(dataset_id=dataset.id))
    if existing:
        client.delete_examples(example_ids=[ex.id for ex in existing])
        print(f"Cleared {len(existing)} existing example(s) before re-upload.")

    inputs, outputs, metadata = [], [], []
    for row in rows:
        inputs.append({
            "target_market": row["target_market"],
            "company_description": row["company_description"],
        })
        outputs.append({"expected_behavior": row["expected_behavior"]})
        metadata.append({
            "case_id": row["case_id"],
            "scenario_type": row["scenario_type"],
            "dataset_version": VERSION_TAG,
        })

    client.create_examples(
        inputs=inputs,
        outputs=outputs,
        metadata=metadata,
        dataset_id=dataset.id,
    )
    print(f"Uploaded {len(rows)} examples to '{DATASET_NAME}' tagged dataset_version={VERSION_TAG}.")

    # Also create a named dataset version/tag if the SDK supports it, so the
    # baseline run can pin against this exact snapshot.
    try:
        client.create_dataset_version(dataset_id=dataset.id, tag=VERSION_TAG)
        print(f"Tagged dataset version '{VERSION_TAG}'.")
    except Exception as e:
        print(f"[note] Could not create a named dataset version/tag ({e}); "
              f"relying on the 'dataset_version' metadata field on each example instead.")


if __name__ == "__main__":
    main()
