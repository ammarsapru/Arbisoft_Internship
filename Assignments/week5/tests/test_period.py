from fin_analyst.agents.period import parse_period


def test_default_period_is_1y():
    window, caveat = parse_period(None)
    assert window == "1Y"
    assert caveat is None


def test_years_within_5_maps_exactly():
    assert parse_period("5 years") == ("5Y", None)
    assert parse_period("2 years") == ("5Y", None)
    assert parse_period("1 year") == ("1Y", None)


def test_years_beyond_5_maps_to_max_with_caveat():
    window, caveat = parse_period("10 years")
    assert window == "MAX"
    assert caveat is not None
    assert "10" in caveat


def test_all_time_phrases_map_to_max_without_caveat():
    for phrase in ("all time", "since IPO", "entire history"):
        window, caveat = parse_period(phrase)
        assert window == "MAX"
        assert caveat is None


def test_ytd_phrases():
    assert parse_period("YTD")[0] == "YTD"
    assert parse_period("year to date")[0] == "YTD"


def test_unparseable_text_defaults_with_caveat():
    window, caveat = parse_period("sometime recently ish")
    assert window == "1Y"
    assert caveat is not None
