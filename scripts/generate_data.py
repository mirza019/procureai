import argparse
import json
from pathlib import Path

from procureai.synthetic.generator import generate_suppliers, inject_deterioration

SIZES = {"small": 20, "medium": 80, "large": 250}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", choices=SIZES, default="small")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    output = Path("data/generated")
    output.mkdir(parents=True, exist_ok=True)
    suppliers = generate_suppliers(SIZES[args.size], args.seed)
    (output / "suppliers.json").write_text(json.dumps(suppliers, indent=2))
    (output / "scenario_ground_truth.json").write_text(
        json.dumps([inject_deterioration(suppliers)], indent=2)
    )
    print(f"Generated {len(suppliers)} synthetic suppliers with seed {args.seed}")


if __name__ == "__main__":
    main()
