"""
LexiLensAI SDK — MCP Server Instrumentation Demo

Shows how an MCP server author gets automatic token visibility
for Claude API calls made inside their tool handlers.

Architecture:
    MCP Client (Claude Desktop / claude-code)
        → calls your MCP tool (e.g. "summarize_document")
            → your tool handler calls Claude API internally
                → LexiLensAI SDK captures token usage automatically

The SDK patches anthropic.messages.create() so you get per-call
token breakdowns, cache hit/miss detection, and cost estimation
without changing your tool implementation code.

Requirements:
    pip install lexilensai-sdk anthropic mcp

Usage:
    # Run as standalone demo (simulates tool calls without real MCP transport):
    python examples/mcp_server_demo.py

    # Then view the report:
    lexilens report

    # For a real MCP server, see the Server class example below.

Note:
    This demo runs the tool handlers directly (no MCP transport) to show
    the instrumentation in action. In production, these handlers would be
    registered with the MCP Server and called via stdio/SSE transport.
"""
import json
import os
import sys

import anthropic

from lexilensai import LexiLens


# ─── Your MCP Tool Handlers ─────────────────────────────────────────────────
# These are normal functions that call the Anthropic API.
# LexiLensAI patches messages.create() so every call is captured automatically.


def summarize_document(document_text: str, max_length: int = 200) -> str:
    """
    MCP tool: Summarize a document using Claude.

    In a real MCP server, this would be registered as a tool handler.
    The SDK captures the Claude API call without any changes to this code.
    """
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_length,
        system="You are a concise summarizer. Produce a brief summary.",
        messages=[
            {"role": "user", "content": f"Summarize this document:\n\n{document_text}"}
        ],
    )

    return response.content[0].text


def analyze_code(code: str, language: str = "python") -> str:
    """
    MCP tool: Analyze code for issues and improvements.

    Makes a Claude API call with a longer system prompt (demonstrating
    how cache behavior varies with prompt changes).
    """
    client = anthropic.Anthropic()

    system_prompt = (
        f"You are a senior {language} code reviewer. "
        "Identify bugs, security issues, and performance problems. "
        "Be concise: list issues as bullet points with severity (high/medium/low). "
        "If the code looks good, say so briefly."
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=system_prompt,
        messages=[
            {"role": "user", "content": f"Review this {language} code:\n\n```{language}\n{code}\n```"}
        ],
    )

    return response.content[0].text


def translate_text(text: str, target_language: str = "Spanish") -> str:
    """
    MCP tool: Translate text to a target language.

    Uses the same system prompt pattern so repeated calls with the
    same target language will benefit from prompt caching.
    """
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=f"You are a translator. Translate the following text to {target_language}. "
               "Output only the translation, nothing else.",
        messages=[
            {"role": "user", "content": text}
        ],
    )

    return response.content[0].text


# ─── MCP Server Structure (for reference) ───────────────────────────────────
#
# In a real MCP server using the `mcp` package, your server looks like this:
#
#     from mcp.server import Server
#     from mcp.server.stdio import stdio_server
#     from lexilensai import LexiLens
#
#     app = Server("my-mcp-server")
#
#     # Initialize LexiLensAI at server startup — patches anthropic automatically
#     lexilens = LexiLens.init(
#         exporter="jsonl",          # or "platform" to send to Docker instance
#         application_id="my-mcp-server",
#         objective="MCP tool calls"
#     )
#
#     @app.list_tools()
#     async def list_tools():
#         return [
#             {"name": "summarize_document", "description": "Summarize a document", ...},
#             {"name": "analyze_code", "description": "Review code for issues", ...},
#         ]
#
#     @app.call_tool()
#     async def call_tool(name: str, arguments: dict):
#         if name == "summarize_document":
#             result = summarize_document(arguments["text"])
#             return [TextContent(type="text", text=result)]
#         elif name == "analyze_code":
#             result = analyze_code(arguments["code"], arguments.get("language", "python"))
#             return [TextContent(type="text", text=result)]
#
#     async def main():
#         async with stdio_server() as (read, write):
#             await app.run(read, write, app.create_initialization_options())
#         lexilens.close()  # Flush on shutdown
#
# That's it. Two lines (init + close) give you full token visibility.
# Every anthropic.messages.create() call made by your tool handlers
# is automatically captured with token counts, latency, and cache metrics.
#
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """
    Demo: simulate MCP tool calls and show LexiLensAI capturing them.
    """
    print("=" * 64)
    print("  LexiLensAI — MCP Server Token Visibility Demo")
    print("=" * 64)
    print()
    print("This simulates an MCP server's tool handlers calling Claude.")
    print("LexiLensAI captures every API call automatically.")
    print()

    # ── Initialize LexiLensAI (this is the ONLY setup needed) ──
    lexilens = LexiLens.init(
        exporter="jsonl",
        application_id="mcp-server-demo",
        objective="Demonstrate MCP server instrumentation",
    )
    print(f"Session: {lexilens.session_id}")
    print(f"Spans:   lexilens_spans.jsonl")
    print()

    # ── Simulate tool calls (as if triggered by an MCP client) ──

    # Tool call 1: summarize_document
    print("─" * 64)
    print("Tool call: summarize_document")
    print("─" * 64)
    document = (
        "LexiLensAI is a session-native runtime intelligence platform for "
        "enterprise multi-agent AI systems. It reconstructs complete execution "
        "sessions from OpenTelemetry traces, builds causal graphs showing how "
        "agents delegated work to each other, detects anomalies like recursive "
        "loops and token explosions, and generates natural-language explanations "
        "of findings using Claude. The platform helps developers understand why "
        "their AI agent costs spiked, which agent caused a failure cascade, and "
        "whether critical instructions were lost during context compaction."
    )
    summary = summarize_document(document)
    print(f"  Result: {summary[:100]}...")
    print()

    # Tool call 2: analyze_code
    print("─" * 64)
    print("Tool call: analyze_code")
    print("─" * 64)
    code = '''
def process_user_input(user_input):
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    result = db.execute(query)
    password = result[0]["password"]
    return eval(f"check_password('{password}')")
'''
    analysis = analyze_code(code, language="python")
    print(f"  Result: {analysis[:120]}...")
    print()

    # Tool call 3: translate_text (same system prompt pattern → cache potential)
    print("─" * 64)
    print("Tool call: translate_text (call 1)")
    print("─" * 64)
    text1 = "The quick brown fox jumps over the lazy dog."
    translation1 = translate_text(text1, target_language="Spanish")
    print(f"  Result: {translation1}")
    print()

    # Tool call 4: translate_text again (same system prompt → should cache)
    print("─" * 64)
    print("Tool call: translate_text (call 2 — same target language)")
    print("─" * 64)
    text2 = "Every great journey begins with a single step."
    translation2 = translate_text(text2, target_language="Spanish")
    print(f"  Result: {translation2}")
    print()

    # ── Close session and flush ──
    lexilens.close()

    print("=" * 64)
    print()
    print("Done! 4 tool calls captured. View your token breakdown:")
    print()
    print("    lexilens report")
    print()
    print("Look for:")
    print("  • Per-call token counts (input/output/cache)")
    print("  • Cache hit on the second translate_text call")
    print("  • Total cost across all tool invocations")
    print("  • Any anomalies (token spikes between calls)")
    print()
    print("To send spans to your running LexiLensAI platform instead:")
    print()
    print('    lexilens = LexiLens.init(exporter="platform")')
    print("    # Then check http://localhost:8000/app for the session")
    print()


if __name__ == "__main__":
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set")
        print()
        print("Usage:")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        print("    python examples/mcp_server_demo.py")
        sys.exit(1)

    main()
