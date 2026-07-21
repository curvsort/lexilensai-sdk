"""
Allow running lexilensai as a module: python -m lexilensai report
"""
import sys

from .report import main as report_main


def main():
    """Module entry point — routes to report by default."""
    # If first arg is "report", strip it and pass remaining to report CLI
    if len(sys.argv) > 1 and sys.argv[0].endswith("__main__.py"):
        # Direct module execution: python -m lexilensai [args]
        pass

    report_main()


if __name__ == "__main__":
    main()
