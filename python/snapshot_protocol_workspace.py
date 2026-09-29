"""Save a current-query baseline for later refresh comparisons (not an export)."""
import argparse
import json
from pathlib import Path

from recording_workspace import evaluate_protocol_file
from workspace_recipes import capture_query, compare_query, save_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol_file", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    definition = json.loads(args.protocol_file.read_text())
    catalog = (args.protocol_file.parent / definition["catalog_ref"]).resolve()
    result = evaluate_protocol_file(args.protocol_file)
    # The initial evaluator's empty result omits context; preserve it explicitly.
    if not result["epochs"]:
        result = {**result, "project_uuid": definition["project_uuid"],
                  "source_revisions": result.get("source_revisions", [])}
    snapshot = capture_query(definition, result, str(catalog))
    delta = compare_query(json.loads(args.compare.read_text()), snapshot) if args.compare else None
    save_snapshot(args.output, snapshot)
    print(json.dumps({"query_snapshot": str(args.output.resolve()),
                      "epochs": len(snapshot["epochs"]), "diff": delta,
                      "data_exported": False}, indent=2))


if __name__ == "__main__":
    main()
