"""Scrapling POC - Testing core features with Python 3.14"""

from scrapling.fetchers import Fetcher


def demo_basic_fetch():
    """Basic HTTP fetch and CSS selectors."""
    print("=" * 60)
    print("1. Basic Fetch - Quotes to Scrape")
    print("=" * 60)

    page = Fetcher.get("https://quotes.toscrape.com/")
    print(f"Status: {page.status}")
    print(f"Page title: {page.css('title::text').get()}")

    quotes = page.css(".quote")
    print(f"Found {len(quotes)} quotes\n")

    for quote in quotes[:3]:
        text = quote.css(".text::text").get()
        author = quote.css(".author::text").get()
        tags = quote.css(".tag::text").getall()
        print(f'  "{text}"')
        print(f"  — {author} | Tags: {', '.join(tags)}\n")


def demo_xpath():
    """XPath selectors."""
    print("=" * 60)
    print("2. XPath Selectors")
    print("=" * 60)

    page = Fetcher.get("https://quotes.toscrape.com/")
    authors = page.xpath('//small[@class="author"]/text()').getall()
    unique_authors = list(dict.fromkeys(authors))
    print(f"Unique authors on page: {', '.join(unique_authors)}\n")


def demo_pagination():
    """Follow pagination links."""
    print("=" * 60)
    print("3. Pagination - Scraping multiple pages")
    print("=" * 60)

    all_quotes = []
    url = "https://quotes.toscrape.com/"

    for page_num in range(1, 4):
        page = Fetcher.get(url)
        quotes = page.css(".quote .text::text").getall()
        all_quotes.extend(quotes)
        print(f"  Page {page_num}: {len(quotes)} quotes")

        next_btn = page.css(".next a")
        if next_btn:
            href = next_btn[0].attrib.get("href", "")
            url = f"https://quotes.toscrape.com{href}"
        else:
            break

    print(f"  Total: {len(all_quotes)} quotes scraped\n")


def demo_find_methods():
    """Different element finding methods."""
    print("=" * 60)
    print("4. Find Methods")
    print("=" * 60)

    page = Fetcher.get("https://quotes.toscrape.com/")

    by_text = page.find_by_text("Albert Einstein")
    print(f"  find_by_text('Albert Einstein'): found = {by_text is not None}, tag = {by_text.tag if by_text else 'N/A'}")

    all_divs = page.find_all("div", class_="quote")
    print(f"  find_all('div', class='quote'): {len(all_divs)} elements")

    links = page.css("a::attr(href)").getall()
    print(f"  All links on page: {len(links)}")
    print()


def demo_dom_navigation():
    """DOM traversal: parent, siblings, children."""
    print("=" * 60)
    print("5. DOM Navigation")
    print("=" * 60)

    page = Fetcher.get("https://quotes.toscrape.com/")
    first_quote = page.css(".quote")[0]

    print(f"  Tag: {first_quote.tag}")
    print(f"  Children count: {len(first_quote.children)}")
    print(f"  Parent tag: {first_quote.parent.tag}")
    print(f"  Has next sibling: {first_quote.next is not None}")
    print()


def demo_raw_html_parsing():
    """Parse raw HTML without fetching."""
    from scrapling.parser import Selector

    print("=" * 60)
    print("6. Raw HTML Parsing")
    print("=" * 60)

    html = """
    <html>
    <body>
        <div class="products">
            <div class="product" data-id="1">
                <h2>Widget A</h2>
                <span class="price">$19.99</span>
            </div>
            <div class="product" data-id="2">
                <h2>Widget B</h2>
                <span class="price">$29.99</span>
            </div>
            <div class="product" data-id="3">
                <h2>Gadget C</h2>
                <span class="price">$9.99</span>
            </div>
        </div>
    </body>
    </html>
    """

    page = Selector(html)
    products = page.css(".product")
    print(f"  Found {len(products)} products:")
    for p in products:
        name = p.css("h2::text").get()
        price = p.css(".price::text").get()
        data_id = p.attrib.get("data-id")
        print(f"    [{data_id}] {name} - {price}")
    print()


def demo_session_fetch():
    """Session-based fetching with impersonation."""
    from scrapling.fetchers import FetcherSession

    print("=" * 60)
    print("7. Session Fetch with Browser Impersonation")
    print("=" * 60)

    with FetcherSession(impersonate="chrome") as session:
        page = session.get(
            "https://httpbin.org/headers", stealthy_headers=True
        )
        print(f"  Status: {page.status}")
        print(f"  Response (first 300 chars): {page.text[:300]}")
    print()


if __name__ == "__main__":
    import sys

    print(f"Python {sys.version}")
    print(f"Scrapling POC\n")

    demo_basic_fetch()
    demo_xpath()
    demo_pagination()
    demo_find_methods()
    demo_dom_navigation()
    demo_raw_html_parsing()
    demo_session_fetch()

    print("=" * 60)
    print("All demos completed!")
    print("=" * 60)
