"""SAIPENVIEW entry point."""
import sys

from saipenview.app import run


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
