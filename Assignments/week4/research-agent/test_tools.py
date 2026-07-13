"""
Direct (agent-free) tests for every skill in research_agent.py.
Run: python test_tools.py
"""

import asyncio

import research_agent as ra


def text_of(result: dict) -> str:
    return result["content"][0]["text"]


async def main() -> None:
    passed = 0

    # 1. read_file on .txt
    out = text_of(await ra.read_file.handler({"path": "sample_notes.txt"}))
    assert "Jakarta" in out, out
    print("PASS read_file(.txt) -> found 'Jakarta'")
    passed += 1

    # 2. read_file on .pdf
    out = text_of(await ra.read_file.handler({"path": "sample_doc.pdf"}))
    assert "15,000" in out, out
    print("PASS read_file(.pdf) -> found budget '15,000'")
    passed += 1

    # 3. read_file error paths
    out = await ra.read_file.handler({"path": "does_not_exist.txt"})
    assert out.get("is_error"), out
    out = await ra.read_file.handler({"path": "make_sample_pdf.py"})
    assert out.get("is_error"), out
    print("PASS read_file error handling (missing file, bad extension)")
    passed += 1

    # 4. memory round-trip
    await ra.remember_fact.handler({"key": "hq_city", "value": "Jakarta"})
    out = text_of(await ra.recall_facts.handler({}))
    assert "hq_city" in out and "Jakarta" in out, out
    print("PASS remember_fact/recall_facts round-trip")
    passed += 1

    # 5. web_search (live SerpApi call)
    out = text_of(await ra.web_search.handler({"query": "Jakarta news today"}))
    assert "http" in out, out
    print(f"PASS web_search -> got results, first line: {out.splitlines()[0][:80]}")
    passed += 1

    # 6. hook writes a timestamped line
    before = ra.LOG_FILE.read_text(encoding="utf-8") if ra.LOG_FILE.exists() else ""
    await ra.log_tool_call(
        {"hook_event_name": "PreToolUse", "tool_name": "unit_test", "tool_input": {"q": 1}},
        None,
        None,
    )
    after = ra.LOG_FILE.read_text(encoding="utf-8")
    new_line = after[len(before):].strip()
    assert "unit_test" in new_line and "T" in new_line.split(" | ")[0], new_line
    print(f"PASS hook logging -> {new_line}")
    passed += 1

    print(f"\n{passed}/6 checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
