"""
Direct (agent-free) tests for every travel-agent skill.
Run: python test_tools.py
Note: flight/hotel checks hit SerpApi live and consume a few searches.
"""

import asyncio
import datetime

import travel_agent as ta


def text_of(result: dict) -> str:
    return result["content"][0]["text"]


async def main() -> None:
    passed = 0
    # future dates ~2 months out so Google Flights always has inventory
    out_date = (datetime.date.today() + datetime.timedelta(days=60)).isoformat()
    ret_date = (datetime.date.today() + datetime.timedelta(days=67)).isoformat()

    # 1. read_file on the trip plan PDF
    out = text_of(await ta.read_file.handler({"path": "trip_plan.pdf"}))
    assert "Istanbul" in out and "3,500" in out, out[:300]
    print("PASS read_file(trip_plan.pdf) -> found 'Istanbul' and budget '3,500'")
    passed += 1

    # 2. read_file error paths
    r = await ta.read_file.handler({"path": "nope.txt"})
    assert r.get("is_error"), r
    r = await ta.read_file.handler({"path": "travel_agent.py"})
    assert r.get("is_error"), r
    print("PASS read_file error handling")
    passed += 1

    # 3. memory round-trip
    await ta.remember_fact.handler({"key": "budget", "value": "3500 USD"})
    out = text_of(await ta.recall_facts.handler({}))
    assert "budget" in out and "3500" in out, out
    print("PASS memory round-trip")
    passed += 1

    # 4. search_flights validation (round_trip without return_date must error)
    r = await ta.search_flights.handler(
        {"departure_id": "LHE", "arrival_id": "IST", "outbound_date": out_date, "trip_type": "round_trip"}
    )
    assert r.get("is_error"), r
    print("PASS search_flights validation (missing return_date rejected)")
    passed += 1

    # 5. search_flights live (one-way LHE -> IST)
    out = text_of(await ta.search_flights.handler(
        {"departure_id": "LHE", "arrival_id": "IST", "outbound_date": out_date, "trip_type": "one_way"}
    ))
    assert "$" in out, out[:300]
    print(f"PASS search_flights live -> {out.splitlines()[0][:90]}")
    passed += 1

    # 6. search_hotels live (Istanbul, budget-capped)
    out = text_of(await ta.search_hotels.handler(
        {"city": "Istanbul, Turkey", "check_in_date": out_date, "check_out_date": ret_date,
         "max_price_per_night_usd": 110}
    ))
    assert "night" in out, out[:300]
    print(f"PASS search_hotels live -> {out.splitlines()[0][:90]}")
    passed += 1

    # 7. hook writes a timestamped line
    before = ta.LOG_FILE.read_text(encoding="utf-8") if ta.LOG_FILE.exists() else ""
    await ta.log_tool_call(
        {"hook_event_name": "PreToolUse", "tool_name": "unit_test", "tool_input": {"x": 1}}, None, None
    )
    after = ta.LOG_FILE.read_text(encoding="utf-8")
    assert "unit_test" in after[len(before):], after[-200:]
    print("PASS hook logging")
    passed += 1

    print(f"\n{passed}/7 checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
