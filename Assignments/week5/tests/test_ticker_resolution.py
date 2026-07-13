from fin_analyst.mcp_server.tools.finance_tools import _KG_TYPE_RE, _TICKER_EXCHANGE_RE, _title_overlap_confidence


def test_ticker_exchange_pattern_matches_known_format():
    assert _TICKER_EXCHANGE_RE.match("AAPL:NASDAQ")
    assert _TICKER_EXCHANGE_RE.match("BRK.A:NYSE")
    assert not _TICKER_EXCHANGE_RE.match("Apple")
    assert not _TICKER_EXCHANGE_RE.match("apple inc")


def test_knowledge_graph_type_pattern_matches_live_format():
    # Confirmed live shape from SerpApi's google engine knowledge_graph.type
    match = _KG_TYPE_RE.match("NASDAQ: TSLA")
    assert match is not None
    assert match.groups() == ("NASDAQ", "TSLA")


def test_title_overlap_confidence_high_for_exact_match():
    assert _title_overlap_confidence("Apple", "Apple Inc") == "high"


def test_title_overlap_confidence_low_for_unrelated_title():
    assert _title_overlap_confidence("SpaceX", "Space Exploration Technologies Corp") == "low"
