import argparse
import importlib.util
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

MODULE_PATH = PROJECT_ROOT / "project" / "demo" / "synthetic_decision_receipt.py"
spec = importlib.util.spec_from_file_location("synthetic_decision_receipt", MODULE_PATH)
synthetic_decision_receipt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(synthetic_decision_receipt)
build_decision_receipt = synthetic_decision_receipt.build_decision_receipt


def main():
    parser = argparse.ArgumentParser(description="Generate a sanitized synthetic decision receipt.")
    parser.add_argument("--case", default="certify-ready", help="Synthetic case id.")
    parser.add_argument(
        "--output",
        default="demo_artifacts/synthetic-decision-receipt.json",
        help="Receipt JSON output path.",
    )
    args = parser.parse_args()

    receipt = build_decision_receipt(args.case)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    main()
