"""Scrapling POC - Testing with peaklab.fr"""

from scrapling.fetchers import Fetcher


def scrape_peaklab():
    print("Fetching peaklab.fr...\n")
    page = Fetcher.get("https://peaklab.fr/", stealthy_headers=True)

    print(f"Status: {page.status}")
    print(f"Title: {page.css('title::text').get()}")
    print(f"Meta description: {page.css('meta[name=description]::attr(content)').get()}")

    print("\n--- Headings ---")
    for level in range(1, 4):
        headings = page.css(f"h{level}::text").getall()
        if headings:
            for h in headings:
                text = h.strip()
                if text:
                    print(f"  H{level}: {text}")

    print("\n--- Links ---")
    links = page.css("a[href]")
    seen = set()
    for link in links:
        href = link.attrib.get("href", "")
        text = link.css("::text").get("").strip()
        if href and href not in seen and not href.startswith("#"):
            seen.add(href)
            label = f" ({text})" if text else ""
            print(f"  {href}{label}")

    print("\n--- Images ---")
    images = page.css("img[src]")
    for img in images:
        src = img.attrib.get("src", "")
        alt = img.attrib.get("alt", "")
        print(f"  {src} | alt: {alt}")

    print("\n--- Meta tags ---")
    metas = page.css("meta[property], meta[name]")
    for meta in metas:
        name = meta.attrib.get("property") or meta.attrib.get("name", "")
        content = meta.attrib.get("content", "")
        if content:
            print(f"  {name}: {content[:100]}")


if __name__ == "__main__":
    scrape_peaklab()
