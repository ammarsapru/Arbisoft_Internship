from fin_analyst.mcp_server.schemas.common import parse_numeric
from fin_analyst.mcp_server.schemas.finance import FinancialStatement, RelativePerformance
from fin_analyst.mcp_server.schemas.raw.finance import RawFinancialLineItem, RawFinancialPeriod, RawFinancialStatement


def test_parse_numeric_handles_suffixes_and_currency():
    assert parse_numeric("$313.39") == 313.39
    assert parse_numeric("4.60T") == 4.6e12
    assert parse_numeric("16.6%") == 16.6
    assert parse_numeric("1,234,567") == 1234567.0


def test_parse_numeric_handles_missing_values():
    assert parse_numeric("—") is None
    assert parse_numeric("N/A") is None
    assert parse_numeric(None) is None


def test_relative_performance_computes_outperformance_via_validator():
    rp = RelativePerformance(benchmark_name="Nasdaq", benchmark_period_return_pct=10.0, stock_period_return_pct=25.0)
    assert rp.outperformance_pct == 15.0


def test_relative_performance_handles_missing_benchmark():
    rp = RelativePerformance(benchmark_name="Nasdaq", benchmark_period_return_pct=None, stock_period_return_pct=25.0)
    assert rp.outperformance_pct is None


def test_financial_statement_from_raw_parses_line_items_and_lookup():
    raw = RawFinancialStatement(
        title="Income statement",
        results=[
            RawFinancialPeriod(
                date="Mar 2026",
                period_type="Quarterly",
                table=[
                    RawFinancialLineItem(title="Revenue", value="111184000000", change="16.6%"),
                    RawFinancialLineItem(title="Net income", value="29578000000", change="19.36%"),
                ],
            )
        ],
    )
    statement = FinancialStatement.from_raw(raw)
    assert statement.statement_name == "Income statement"
    period = statement.periods[0]
    revenue = period.get("Revenue")
    assert revenue is not None
    assert revenue.parsed_value == 111184000000.0
    assert period.get("Nonexistent Line Item") is None
