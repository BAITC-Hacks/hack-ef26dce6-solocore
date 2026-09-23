"""Command-line entry point for fixture generation and the naive baseline."""

from __future__ import annotations

import argparse

from procure.calc.naive import calculate_naive
from procure.data.generate import generate_dataset


def main() -> None:
    """Run the selected currently available pipeline action."""
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--generate", action="store_true")
    actions.add_argument("--naive", action="store_true")
    arguments = parser.parse_args()

    if arguments.generate:
        generate_dataset()
    elif arguments.naive:
        print(calculate_naive().to_string(index=False))
    else:
        print("pipeline not implemented")


if __name__ == "__main__":
    main()
