"""Stepwise Excel report builder using XlsxWriter (chosen over openpyxl for
its stronger from-scratch chart support - see plan.md). One method per
sheet, built up incrementally by WorkbookBuilder.build().
"""

from pathlib import Path

import xlsxwriter

from fin_analyst.mcp_server.schemas.finance import FinancialBundle
from fin_analyst.mcp_server.schemas.news import NewsImpactBundle

SHEET_NAMES = ["Overview", "Price & Technicals", "Fundamentals", "Relative Performance", "News & Impact"]


class WorkbookBuilder:
    def __init__(self, path: Path, bundle: FinancialBundle, news: NewsImpactBundle | None, executive_summary: str):
        self.path = path
        self.bundle = bundle
        self.news = news
        self.executive_summary = executive_summary
        self.workbook = xlsxwriter.Workbook(str(path))
        self._fmt_header = self.workbook.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white"})
        self._fmt_title = self.workbook.add_format({"bold": True, "font_size": 14})
        self._fmt_pct_up = self.workbook.add_format({"font_color": "#0B7A0B"})
        self._fmt_pct_down = self.workbook.add_format({"font_color": "#B00000"})
        self._fmt_wrap = self.workbook.add_format({"text_wrap": True, "valign": "top"})

    def build(self) -> Path:
        self._build_overview_sheet()
        self._build_price_sheet()
        self._build_fundamentals_sheet()
        self._build_relative_performance_sheet()
        self._build_news_sheet()
        self.workbook.close()
        return self.path

    def _pct_format(self, value: float | None):
        if value is None:
            return self._fmt_wrap
        return self._fmt_pct_up if value >= 0 else self._fmt_pct_down

    def _build_overview_sheet(self) -> None:
        ws = self.workbook.add_worksheet("Overview")
        ws.set_column("A:A", 28)
        ws.set_column("B:B", 60)

        ws.write("A1", f"{self.bundle.company_name} ({self.bundle.ticker}:{self.bundle.summary.exchange})", self._fmt_title)
        ws.write("A2", "Executive Summary", self._fmt_header)
        ws.merge_range("A3:B8", self.executive_summary, self._fmt_wrap)

        row = 10
        ws.write(row, 0, "Metric", self._fmt_header)
        ws.write(row, 1, "Value", self._fmt_header)
        row += 1

        summary = self.bundle.summary
        rows = [
            ("Current price", f"{summary.currency} {summary.price:,.2f}"),
            (
                "Today's movement",
                f"{summary.price_movement.direction} {summary.price_movement.percentage:.2f}%"
                if summary.price_movement
                else "n/a",
            ),
            ("As of", summary.as_of),
            ("Analyzed period", f"{self.bundle.period.resolved_window} (requested: {self.bundle.period.raw_text or 'default'})"),
        ]
        if self.bundle.period.caveat:
            rows.append(("Period caveat", self.bundle.period.caveat))
        rows.append(("Net margin %", f"{self.bundle.net_margin_pct:.2f}%" if self.bundle.net_margin_pct is not None else "n/a"))

        if self.news is not None and self.news.aggregate_impact_score is not None:
            rows.append(
                (
                    "Aggregate news impact score",
                    f"{self.news.aggregate_impact_score:.2f} ({len(self.news.scores)} articles - see News & Impact sheet)",
                )
            )

        for label, value in rows:
            ws.write(row, 0, label)
            ws.write(row, 1, value)
            row += 1

        row += 1
        ws.write(row, 0, "Key Stats", self._fmt_header)
        ws.write(row, 1, "", self._fmt_header)
        row += 1
        for stat in self.bundle.key_stats:
            ws.write(row, 0, stat.label)
            ws.write(row, 1, stat.raw_value)
            row += 1

        if self.bundle.profile.description:
            row += 1
            ws.write(row, 0, "Company Profile", self._fmt_header)
            row += 1
            ws.merge_range(row, 0, row + 6, 1, self.bundle.profile.description[:2000], self._fmt_wrap)

    def _build_price_sheet(self) -> None:
        ws = self.workbook.add_worksheet("Price & Technicals")
        ws.write_row(0, 0, ["Date", "Price", "Volume"], self._fmt_header)

        for i, point in enumerate(self.bundle.price_history, start=1):
            ws.write(i, 0, point.date.strftime("%Y-%m-%d"))
            ws.write(i, 1, point.price)
            ws.write(i, 2, point.volume if point.volume is not None else "")

        n = len(self.bundle.price_history)
        if n > 1:
            chart = self.workbook.add_chart({"type": "line"})
            chart.add_series(
                {
                    "name": f"{self.bundle.ticker} price",
                    "categories": ["Price & Technicals", 1, 0, n, 0],
                    "values": ["Price & Technicals", 1, 1, n, 1],
                }
            )
            chart.set_title({"name": f"{self.bundle.ticker} price - {self.bundle.period.resolved_window}"})
            chart.set_size({"width": 720, "height": 400})
            ws.insert_chart("E1", chart)

        t = self.bundle.technicals
        row = n + 3
        ws.write(row, 0, "Technical Indicator", self._fmt_header)
        ws.write(row, 1, "Value", self._fmt_header)
        for label, value in [
            ("Period return %", t.period_return_pct),
            ("Volatility % (stdev of daily returns)", t.volatility_pct),
            ("Max drawdown %", t.max_drawdown_pct),
            ("SMA (last 20 points)", t.sma_20),
            ("EMA (last 20 points)", t.ema_20),
        ]:
            row += 1
            ws.write(row, 0, label)
            ws.write(row, 1, round(value, 4) if value is not None else "n/a")

    def _build_fundamentals_sheet(self) -> None:
        ws = self.workbook.add_worksheet("Fundamentals")
        ws.set_column("A:A", 32)
        row = 0
        for statement in self.bundle.statements:
            ws.write(row, 0, statement.statement_name, self._fmt_title)
            row += 1
            if not statement.periods:
                row += 1
                continue

            periods = statement.periods[:8]
            ws.write(row, 0, "Line Item", self._fmt_header)
            for col, period in enumerate(periods, start=1):
                ws.write(row, col, f"{period.period_label} ({period.period_type})", self._fmt_header)
            row += 1

            line_titles = list(dict.fromkeys(item.title for item in periods[0].line_items)) if periods else []
            for title in line_titles:
                ws.write(row, 0, title)
                for col, period in enumerate(periods, start=1):
                    item = period.get(title)
                    ws.write(row, col, item.parsed_value if item and item.parsed_value is not None else (item.raw_value if item else ""))
                row += 1
            row += 2

    def _build_relative_performance_sheet(self) -> None:
        ws = self.workbook.add_worksheet("Relative Performance")
        ws.set_column("A:A", 32)
        rp = self.bundle.relative_performance
        if rp is None:
            ws.write(0, 0, "Relative performance data unavailable for this run.")
            return

        ws.write_row(0, 0, ["Metric", "Value"], self._fmt_header)
        rows = [
            (f"{self.bundle.ticker} period return %", rp.stock_period_return_pct),
            (f"{rp.benchmark_name} period return %", rp.benchmark_period_return_pct),
            ("Outperformance vs. benchmark %", rp.outperformance_pct),
        ]
        for i, (label, value) in enumerate(rows, start=1):
            ws.write(i, 0, label)
            ws.write(i, 1, round(value, 4) if value is not None else "n/a", self._pct_format(value))

    def _build_news_sheet(self) -> None:
        ws = self.workbook.add_worksheet("News & Impact")
        ws.set_column("A:A", 50)
        ws.set_column("B:E", 14)
        ws.write_row(0, 0, ["Article", "Sentiment", "Magnitude", "Recency Weight", "Composite Score"], self._fmt_header)

        if self.news is None or not self.news.scores:
            ws.write(1, 0, "No news impact data available for this run.")
            return

        ordered = sorted(self.news.scores, key=lambda s: s.composite_score, reverse=True)
        for i, score in enumerate(ordered, start=1):
            ws.write_url(i, 0, score.article_link, string=score.article_title)
            ws.write(i, 1, score.sentiment)
            ws.write(i, 2, score.magnitude)
            ws.write(i, 3, round(score.recency_weight, 3))
            ws.write(i, 4, round(score.composite_score, 3), self._pct_format(score.composite_score))

        row = len(ordered) + 2
        ws.write(row, 0, "Aggregate impact score", self._fmt_header)
        ws.write(row, 1, round(self.news.aggregate_impact_score, 3) if self.news.aggregate_impact_score is not None else "n/a")
