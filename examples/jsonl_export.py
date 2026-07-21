"""
JSONL Export Example.

Demonstrates using the JSONL exporter to write spans to a local file.
Useful for testing and offline replay.
"""
from lexilensai import LexiLens


def main():
    """Run agent with JSONL export."""
    print("=== JSONL Export Example ===\n")

    # Initialize with JSONL exporter
    lexilens = LexiLens.init(
        tenant_id="demo",
        application_id="jsonl_example",
        exporter="jsonl",
        objective="Test JSONL export"
    )

    print(f"Session ID: {lexilens.session_id}")
    print("Spans will be written to: lexilens_spans.jsonl\n")

    # Simulate some work (no Strands required for this demo)
    print("Session started — span written to file.")

    # Close
    lexilens.close()
    print("Session ended — span written to file.\n")

    # Read and display the file
    print("=== Contents of lexilens_spans.jsonl ===\n")
    try:
        with open("lexilens_spans.jsonl", "r") as f:
            for line in f:
                print(line.strip())
    except FileNotFoundError:
        print("File not found (this shouldn't happen)")

    print("\n=== Example complete ===")
    print("You can now:")
    print("1. Inspect lexilens_spans.jsonl")
    print("2. Replay spans through the platform's span_normalizer.py")
    print("3. Use this file for integration tests")


if __name__ == "__main__":
    main()
