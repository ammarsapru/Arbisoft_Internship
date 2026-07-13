from fin_analyst.mcp_server.clients.serpapi_client import get_serpapi_client
from fin_analyst.mcp_server.schemas.news import NewsArticle
from fin_analyst.mcp_server.schemas.raw.news import RawGoogleNewsResponse


async def get_company_news(ticker: str, company_name: str, max_articles: int = 15) -> list[NewsArticle]:
    """Fetch recent news coverage for a company via SerpApi's dedicated
    Google News engine (not the embedded news_results on the Finance API
    response, which — confirmed live — lacks `iso_date` and is therefore
    unusable for the recency-decay weighting News Impact scoring depends on).

    `q` combines company name and ticker to reduce false positives from
    similarly-named companies. (Note: SerpApi's documented `so=1`
    sort-by-date parameter returned HTTP 400 in live testing against this
    engine, so results are left at Google's default relevance ranking,
    which in practice still skews heavily toward recent coverage.)
    """
    client = get_serpapi_client()
    data = await client.search("google_news", q=f"{company_name} {ticker} stock", hl="en", gl="us")
    raw = RawGoogleNewsResponse.model_validate(data)

    articles = []
    for item in raw.news_results[:max_articles]:
        article = NewsArticle.from_raw(item)
        if article is not None:
            articles.append(article)
    return articles
