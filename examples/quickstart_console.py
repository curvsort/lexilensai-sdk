"""
LexiLensAI SDK — Console Exporter Quickstart

Minimal example demonstrating SDK initialization and session lifecycle
without requiring Strands or any agent framework.

Useful for testing SDK installation and basic span emission.
"""
from lexilensai import LexiLens


def main():
    """Demonstrate basic SDK lifecycle with console exporter."""
    print("=" * 60)
    print("LexiLensAI SDK — Console Exporter Quickstart")
    print("=" * 60)
    print()

    # Initialize with console exporter (no backend required)
    print("Initializing LexiLens...")
    lexilens = LexiLens.init(
        tenant_id="demo",
        application_id="console_test",
        exporter="console",  # Prints spans to stdout
        objective="Verify SDK installation"
    )

    print(f"\n✓ Initialized successfully")
    print(f"  Session ID: {lexilens.session_id}")
    print(f"  Tenant: {lexilens.config.tenant_id}")
    print(f"  Application: {lexilens.config.application_id}")
    print(f"  Exporter: {lexilens.config.exporter}")
    print()

    print("-" * 60)
    print("Emitted spans will appear above/below this line")
    print("-" * 60)
    print()

    # Close session (emits session.end span)
    print("Closing session...")
    lexilens.close()

    print()
    print("=" * 60)
    print("✓ Quickstart complete")
    print("=" * 60)
    print()
    print("What happened:")
    print("  1. session.start span emitted on init()")
    print("  2. session.end span emitted on close()")
    print("  3. Both printed to console (check output above)")
    print()
    print("Next steps:")
    print("  - Try examples/quickstart.py for Strands integration")
    print("  - Try examples/production_demo.ipynb for full workflow")
    print("  - Switch exporter='jsonl' to write spans to file")
    print("  - Switch exporter='otel' to send to OTel collector")
    print()


if __name__ == "__main__":
    main()
