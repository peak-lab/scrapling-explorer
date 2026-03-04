"""Scrapling POC - FastAPI Web Interface"""

import json
import time
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from scrapling.fetchers import Fetcher

app = FastAPI(title="Scrapling POC")
templates = Jinja2Templates(directory="templates")


class ScrapeRequest(BaseModel):
    url: str


def analyze_seo(data: dict, page) -> dict:
    title = data["title"]
    meta_desc = data["meta_description"]
    headings = data["headings"]
    links = data["links"]
    images = data["images"]
    metas = data["metas"]
    url = data["url"]

    canonical = page.css("link[rel=canonical]::attr(href)").get(None)
    robots = page.css("meta[name=robots]::attr(content)").get(None)
    lang = page.css("html::attr(lang)").get(None)
    charset = page.css("meta::attr(charset)").get(None)
    viewport = page.css("meta[name=viewport]::attr(content)").get(None)

    ld_json_elements = page.css('script[type="application/ld+json"]')
    structured_data_count = len(ld_json_elements)
    ld_types = []
    for el in ld_json_elements:
        try:
            content = el.css("::text").get("")
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "@type" in parsed:
                ld_types.append(parsed["@type"])
            elif isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "@type" in item:
                        ld_types.append(item["@type"])
        except (json.JSONDecodeError, TypeError):
            pass

    h1_count = sum(1 for h in headings if h["level"] == 1)

    meta_names = {m["name"].lower(): m["content"] for m in metas}
    parsed_url = urlparse(url)

    checks = []

    def add(category, name, status, message):
        checks.append({"category": category, "name": name, "status": status, "message": message})

    if title:
        add("Title", "Title present", "pass", "Title tag is defined.")
    else:
        add("Title", "Title present", "fail", "Missing title tag — add a unique title for this page.")

    if title:
        tlen = len(title)
        if 30 <= tlen <= 60:
            add("Title", "Title length", "pass", f"Title is {tlen} chars (ideal: 30-60).")
        elif tlen < 30:
            add("Title", "Title length", "warn", f"Title is {tlen} chars — consider expanding to 30-60 for better CTR.")
        else:
            add("Title", "Title length", "warn", f"Title is {tlen} chars — may be truncated in SERPs (ideal: 30-60).")

    if meta_desc:
        add("Meta Description", "Description present", "pass", "Meta description is defined.")
    else:
        add("Meta Description", "Description present", "fail", "Missing meta description — add one to improve click-through rate.")

    if meta_desc:
        dlen = len(meta_desc)
        if 120 <= dlen <= 160:
            add("Meta Description", "Description length", "pass", f"Description is {dlen} chars (ideal: 120-160).")
        elif dlen < 120:
            add("Meta Description", "Description length", "warn", f"Description is {dlen} chars — consider expanding to 120-160.")
        else:
            add("Meta Description", "Description length", "warn", f"Description is {dlen} chars — may be truncated (ideal: 120-160).")

    if h1_count == 1:
        add("Headings", "Single H1", "pass", "Page has exactly one H1 tag.")
    elif h1_count == 0:
        add("Headings", "Single H1", "fail", "No H1 tag found — add one as the main heading.")
    else:
        add("Headings", "Single H1", "warn", f"Found {h1_count} H1 tags — use only one per page.")

    levels_present = sorted(set(h["level"] for h in headings))
    hierarchy_ok = True
    for i in range(len(levels_present) - 1):
        if levels_present[i + 1] - levels_present[i] > 1:
            hierarchy_ok = False
            break
    if hierarchy_ok and levels_present:
        add("Headings", "Heading hierarchy", "pass", "Heading levels follow a logical order.")
    elif levels_present:
        add("Headings", "Heading hierarchy", "warn", f"Heading hierarchy skips levels ({' → '.join(f'H{l}' for l in levels_present)}) — maintain sequential order.")
    else:
        add("Headings", "Heading hierarchy", "fail", "No headings found — add headings to structure content.")

    if images:
        with_alt = sum(1 for img in images if img["alt"].strip())
        pct = round(with_alt / len(images) * 100)
        missing = len(images) - with_alt
        if pct == 100:
            add("Images", "Image alt attributes", "pass", "All images have alt text.")
        elif pct >= 80:
            add("Images", "Image alt attributes", "warn", f"{missing} image(s) missing alt text ({pct}% have it).")
        else:
            add("Images", "Image alt attributes", "fail", f"{missing} image(s) missing alt text ({pct}% have it) — add descriptive alt for accessibility and SEO.")
    else:
        add("Images", "Image alt attributes", "pass", "No images to check.")

    internal = sum(1 for l in links if urlparse(l["href"]).netloc in ("", parsed_url.netloc))
    external = len(links) - internal
    if links:
        add("Links", "Internal/external ratio", "pass" if internal > 0 else "warn",
            f"{internal} internal, {external} external links.")
    else:
        add("Links", "Internal/external ratio", "warn", "No links found on this page.")

    empty_anchor = sum(1 for l in links if not l["text"].strip())
    if empty_anchor == 0:
        add("Links", "Anchor text", "pass", "All links have descriptive anchor text.")
    else:
        add("Links", "Anchor text", "warn", f"{empty_anchor} link(s) without anchor text — add descriptive text for better SEO.")

    og_title = meta_names.get("og:title", "")
    og_desc = meta_names.get("og:description", "")
    og_image = meta_names.get("og:image", "")
    og_count = sum(1 for v in [og_title, og_desc, og_image] if v)
    if og_count == 3:
        add("Open Graph", "OG tags", "pass", "og:title, og:description, og:image are all present.")
    elif og_count > 0:
        missing_og = [t for t, v in [("og:title", og_title), ("og:description", og_desc), ("og:image", og_image)] if not v]
        add("Open Graph", "OG tags", "warn", f"Missing: {', '.join(missing_og)}.")
    else:
        add("Open Graph", "OG tags", "fail", "No Open Graph tags — add og:title, og:description, og:image for social sharing.")

    twitter_card = meta_names.get("twitter:card", "")
    if twitter_card:
        add("Open Graph", "Twitter Card", "pass", f"Twitter Card is set ({twitter_card}).")
    else:
        add("Open Graph", "Twitter Card", "warn", "No Twitter Card meta — add twitter:card for better Twitter previews.")

    if canonical:
        add("Technical", "Canonical URL", "pass", f"Canonical is set: {canonical}")
    else:
        add("Technical", "Canonical URL", "warn", "No canonical URL — add one to prevent duplicate content issues.")

    if lang:
        add("Technical", "Language", "pass", f"Language attribute is set ({lang}).")
    else:
        add("Technical", "Language", "warn", "No lang attribute on <html> — add it for accessibility and SEO.")

    if viewport:
        add("Technical", "Viewport", "pass", "Viewport meta tag is defined.")
    else:
        add("Technical", "Viewport", "fail", "No viewport meta — add it for mobile responsiveness.")

    if structured_data_count > 0:
        types_str = ", ".join(ld_types) if ld_types else "detected"
        add("Technical", "Structured data", "pass", f"{structured_data_count} JSON-LD block(s) found ({types_str}).")
    else:
        add("Technical", "Structured data", "warn", "No JSON-LD structured data — consider adding Schema.org markup for rich results.")

    max_score = len(checks) * 2
    raw_score = sum(2 if c["status"] == "pass" else 1 if c["status"] == "warn" else 0 for c in checks)
    score = round(raw_score / max_score * 100) if max_score > 0 else 0

    return {
        "canonical": canonical,
        "robots": robots,
        "lang": lang,
        "charset": charset,
        "viewport": viewport,
        "structured_data_count": structured_data_count,
        "structured_data_types": ld_types,
        "h1_count": h1_count,
        "score": score,
        "checks": checks,
    }


def scrape_url(url: str) -> dict:
    start = time.time()
    page = Fetcher.get(url, stealthy_headers=True)
    elapsed = round(time.time() - start, 2)

    title = page.css("title::text").get("")
    meta_desc = page.css("meta[name=description]::attr(content)").get("")

    headings = []
    for level in range(1, 4):
        for h in page.css(f"h{level}"):
            text = h.css("::text").getall()
            joined = " ".join(t.strip() for t in text if t.strip())
            if joined:
                headings.append({"level": level, "text": joined})

    links = []
    seen = set()
    for a in page.css("a[href]"):
        href = a.attrib.get("href", "")
        text = " ".join(t.strip() for t in a.css("::text").getall() if t.strip())
        if href and href not in seen and not href.startswith("#"):
            seen.add(href)
            links.append({"href": href, "text": text})

    images = []
    for img in page.css("img[src]"):
        images.append({
            "src": img.attrib.get("src", ""),
            "alt": img.attrib.get("alt", ""),
        })

    metas = []
    for meta in page.css("meta[property], meta[name]"):
        name = meta.attrib.get("property") or meta.attrib.get("name", "")
        content = meta.attrib.get("content", "")
        if content:
            metas.append({"name": name, "content": content})

    data = {
        "url": url,
        "status": page.status,
        "elapsed": elapsed,
        "title": title,
        "meta_description": meta_desc,
        "headings": headings,
        "links": links,
        "images": images,
        "metas": metas,
        "stats": {
            "headings": len(headings),
            "links": len(links),
            "images": len(images),
            "metas": len(metas),
        },
    }

    data["seo"] = analyze_seo(data, page)

    return data


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/scrape")
async def scrape(body: ScrapeRequest):
    url = body.url.strip()
    if not url.startswith("http"):
        url = f"https://{url}"
    data = scrape_url(url)
    return data
