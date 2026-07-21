"""
LexiLensAI SDK Quickstart Example.

Demonstrates basic usage with a single Strands agent.
"""
from lexilensai import LexiLens


def main():
    """Run a simple instrumented agent."""
    print("=== LexiLensAI SDK Quickstart ===\n")

    # Initialize instrumentation
    print("Initializing LexiLens...")
    lexilens = LexiLens.init(
        tenant_id="demo",
        application_id="quickstart",
        exporter="console",  # Print spans to console for demo
        objective="Demonstrate basic SDK usage"
    )

    print(f"Session ID: {lexilens.session_id}\n")

    # Import Strands after initialization (so patching works)
    try:
        from strands import Agent

        # Create and run agent
        print("Creating agent...")
        agent = Agent(system_prompt="You are a helpful assistant.")

        print("Running agent...\n")
        result = agent("What is 2+2?")

        print(f"\nAgent response: {result}\n")

    except ImportError:
        print("NOTE: strands package not installed.")
        print("Install with: pip install strands-agents")
        print("\nThe SDK still works — spans were emitted for session start/end.\n")

    # Close and flush
    print("Closing session...")
    lexilens.close()

    print("\n=== Quickstart complete ===")
    print("Check the console output above to see emitted spans.")


if __name__ == "__main__":
    main()
