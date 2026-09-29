"""Evaluate one saved protocol workspace using its main-catalog reference."""
import argparse
import json

from recording_workspace import evaluate_protocol_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol_file")
    parser.add_argument("--identities", action="store_true", help="Include stable epoch/cell identities")
    args = parser.parse_args()
    result = evaluate_protocol_file(args.protocol_file)
    if args.identities:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"protocol_uuid": result["protocol_uuid"],
                          "cells": len(result["cells"]), "epochs": len(result["epochs"])}, indent=2))


if __name__ == "__main__":
    main()
