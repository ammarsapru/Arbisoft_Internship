from fin_analyst.mcp_server.schemas.reference import CompanyReference, TopCompaniesList

_TOP_COMPANIES: list[CompanyReference] = [
    CompanyReference(company_name="Apple Inc", ticker="AAPL", exchange="NASDAQ"),
    CompanyReference(company_name="Microsoft Corp", ticker="MSFT", exchange="NASDAQ"),
    CompanyReference(company_name="Alphabet Inc (Google)", ticker="GOOGL", exchange="NASDAQ"),
    CompanyReference(company_name="Amazon.com Inc", ticker="AMZN", exchange="NASDAQ"),
    CompanyReference(company_name="NVIDIA Corp", ticker="NVDA", exchange="NASDAQ"),
    CompanyReference(company_name="Meta Platforms Inc", ticker="META", exchange="NASDAQ"),
    CompanyReference(company_name="Tesla Inc", ticker="TSLA", exchange="NASDAQ"),
    CompanyReference(company_name="Berkshire Hathaway Inc", ticker="BRK.B", exchange="NYSE"),
    CompanyReference(company_name="Eli Lilly and Co", ticker="LLY", exchange="NYSE"),
    CompanyReference(company_name="JPMorgan Chase & Co", ticker="JPM", exchange="NYSE"),
    CompanyReference(company_name="Visa Inc", ticker="V", exchange="NYSE"),
    CompanyReference(company_name="Walmart Inc", ticker="WMT", exchange="NYSE"),
    CompanyReference(company_name="UnitedHealth Group Inc", ticker="UNH", exchange="NYSE"),
    CompanyReference(company_name="Exxon Mobil Corp", ticker="XOM", exchange="NYSE"),
    CompanyReference(company_name="Mastercard Inc", ticker="MA", exchange="NYSE"),
    CompanyReference(company_name="Procter & Gamble Co", ticker="PG", exchange="NYSE"),
    CompanyReference(company_name="Johnson & Johnson", ticker="JNJ", exchange="NYSE"),
    CompanyReference(company_name="Home Depot Inc", ticker="HD", exchange="NYSE"),
    CompanyReference(company_name="Chevron Corp", ticker="CVX", exchange="NYSE"),
    CompanyReference(company_name="Merck & Co Inc", ticker="MRK", exchange="NYSE"),
]


def get_top_companies() -> TopCompaniesList:
    """Static resource content - no API calls, no runtime dependency.
    Contrast with report_resource.py's finance-report://{ticker}, which is
    empty until a tool populates it: this resource is available immediately
    on server start, precisely because it's hand-curated reference data
    rather than a cache of computed results."""
    return TopCompaniesList(companies=_TOP_COMPANIES)
