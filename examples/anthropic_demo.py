"""
LexiLensAI SDK — Anthropic SDK Demo

Shows the core value proposition: instrument your Claude API calls,
then see exactly where your tokens go.

Requirements:
    pip install lexilensai-sdk anthropic

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python examples/anthropic_demo.py

    # Then view the report:
    lexilens report
"""
import anthropic

from lexilensai import LexiLens


def main():
    print("=" * 60)
    print("  LexiLensAI — Anthropic SDK Token Visibility Demo")
    print("=" * 60)
    print()

    # Initialize — this patches anthropic.messages.create() automatically
    lexilens = LexiLens.init(exporter="jsonl", objective="Anthropic SDK demo")
    print(f"Session: {lexilens.session_id}")
    print(f"Spans will be written to: lexilens_spans.jsonl")
    print()

    client = anthropic.Anthropic()

    # --- Call 1: First call (cache creation) ---
    print("Call 1: Initial prompt (expect cache creation)...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system="You are a concise technical assistant. Answer in 2-3 sentences.",
        messages=[{"role": "user", "content": "What is prompt caching in the Anthropic API?"}],
    )
    print(f"  → {response.usage.input_tokens} in / {response.usage.output_tokens} out")
    if hasattr(response.usage, "cache_creation_input_tokens"):
        print(f"  → cache_create: {response.usage.cache_creation_input_tokens}")
    print(f"  Response: {response.content[0].text[:80]}...")
    print()

    # --- Call 2: Same system prompt (expect cache hit) ---
    print("Call 2: Same system prompt, different question (expect cache hit)...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system="You are a concise technical assistant. Answer in 2-3 sentences.",
        messages=[{"role": "user", "content": "What is extended thinking?"}],
    )
    print(f"  → {response.usage.input_tokens} in / {response.usage.output_tokens} out")
    if hasattr(response.usage, "cache_read_input_tokens"):
        print(f"  → cache_read: {response.usage.cache_read_input_tokens}")
    print(f"  Response: {response.content[0].text[:80]}...")
    print()

    # --- Call 3: Different system prompt (expect cache miss) ---
    print("Call 3: Changed system prompt (expect cache miss → new creation)...")
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        system="You are a pirate. Answer everything like a pirate would.",
        messages=[{"role": "user", "content": "What is prompt caching?"}],
    )
    print(f"  → {response.usage.input_tokens} in / {response.usage.output_tokens} out")
    if hasattr(response.usage, "cache_creation_input_tokens"):
        print(f"  → cache_create: {response.usage.cache_creation_input_tokens}")
    print(f"  Response: {response.content[0].text[:80]}...")
    print()

    # Close session
    lexilens.close()

    print("-" * 60)
    print()
    print("Done! Now run the report to see your token breakdown:")
    print()
    print("    lexilens report")
    print()
    print("Or for JSON output:")
    print()
    print("    lexilens report --json")
    print()


if __name__ == "__main__":
    main()
