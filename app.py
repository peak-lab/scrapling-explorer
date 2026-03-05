"""Scrapling POC - FastAPI Web Interface"""

import ipaddress
import json
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from scrapling.fetchers import Fetcher

app = FastAPI(title="Scrapling POC")
templates = Jinja2Templates(directory="templates")


class ScrapeRequest(BaseModel):
    url: str


def _is_safe_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    try:
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_reserved:
                return False
    except (socket.gaierror, ValueError):
        return False
    return True


def fetch_resource(url, timeout=5):
    if not _is_safe_url(url):
        return None
    try:
        page = Fetcher.get(url, stealthy_headers=True, timeout=timeout)
        return page if page.status == 200 else None
    except Exception:
        return None


def _parse_dates_from_text(text):
    matches = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
    dates = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for m in matches:
        try:
            d = datetime.strptime(m, "%Y-%m-%d")
            if d.year >= 2000 and d <= now:
                dates.append(d)
        except ValueError:
            continue
    return dates


def add(checks, category, name, status, message):
    checks.append({"category": category, "name": name, "status": status, "message": message})


def check_title(title):
    checks = []
    if title:
        add(checks, "Title", "Title present", "pass", "Title tag is defined.")
        tlen = len(title)
        if 30 <= tlen <= 60:
            add(checks, "Title", "Title length", "pass", f"Title is {tlen} chars (ideal: 30-60).")
        elif tlen < 30:
            add(checks, "Title", "Title length", "warn", f"Title is {tlen} chars — consider expanding to 30-60 for better CTR.")
        else:
            add(checks, "Title", "Title length", "warn", f"Title is {tlen} chars — may be truncated in SERPs (ideal: 30-60).")
    else:
        add(checks, "Title", "Title present", "fail", "Missing title tag — add a unique title for this page.")
    return checks


def check_meta_description(meta_desc):
    checks = []
    if meta_desc:
        add(checks, "Meta Description", "Description present", "pass", "Meta description is defined.")
        dlen = len(meta_desc)
        if 120 <= dlen <= 160:
            add(checks, "Meta Description", "Description length", "pass", f"Description is {dlen} chars (ideal: 120-160).")
        elif dlen < 120:
            add(checks, "Meta Description", "Description length", "warn", f"Description is {dlen} chars — consider expanding to 120-160.")
        else:
            add(checks, "Meta Description", "Description length", "warn", f"Description is {dlen} chars — may be truncated (ideal: 120-160).")
    else:
        add(checks, "Meta Description", "Description present", "fail", "Missing meta description — add one to improve click-through rate.")
    return checks


def check_headings(headings):
    checks = []
    h1_count = sum(1 for h in headings if h["level"] == 1)
    if h1_count == 1:
        add(checks, "Headings", "Single H1", "pass", "Page has exactly one H1 tag.")
    elif h1_count == 0:
        add(checks, "Headings", "Single H1", "fail", "No H1 tag found — add one as the main heading.")
    else:
        add(checks, "Headings", "Single H1", "warn", f"Found {h1_count} H1 tags — use only one per page.")

    levels_present = sorted(set(h["level"] for h in headings))
    hierarchy_ok = True
    for i in range(len(levels_present) - 1):
        if levels_present[i + 1] - levels_present[i] > 1:
            hierarchy_ok = False
            break
    if hierarchy_ok and levels_present:
        add(checks, "Headings", "Heading hierarchy", "pass", "Heading levels follow a logical order.")
    elif levels_present:
        add(checks, "Headings", "Heading hierarchy", "warn", f"Heading hierarchy skips levels ({' → '.join(f'H{l}' for l in levels_present)}) — maintain sequential order.")
    else:
        add(checks, "Headings", "Heading hierarchy", "fail", "No headings found — add headings to structure content.")
    return checks


def check_images(images, page):
    checks = []
    if images:
        with_alt = sum(1 for img in images if img["alt"].strip())
        pct = round(with_alt / len(images) * 100)
        missing = len(images) - with_alt
        if pct == 100:
            add(checks, "Images", "Image alt attributes", "pass", "All images have alt text.")
        elif pct >= 80:
            add(checks, "Images", "Image alt attributes", "warn", f"{missing} image(s) missing alt text ({pct}% have it).")
        else:
            add(checks, "Images", "Image alt attributes", "fail", f"{missing} image(s) missing alt text ({pct}% have it) — add descriptive alt for accessibility and SEO.")

        lazy_count = sum(1 for img in images if img.get("loading") == "lazy")
        lazy_pct = round(lazy_count / len(images) * 100)
        if lazy_pct >= 80:
            add(checks, "Images", "Lazy loading", "pass", f"{lazy_pct}% of images use lazy loading ({lazy_count}/{len(images)}).")
        elif lazy_count > 0:
            add(checks, "Images", "Lazy loading", "warn", f"Only {lazy_pct}% of images use lazy loading ({lazy_count}/{len(images)}).")
        elif len(images) > 5:
            add(checks, "Images", "Lazy loading", "warn", f"No images use lazy loading — consider adding loading=\"lazy\" for below-the-fold images ({len(images)} images found).")
        else:
            add(checks, "Images", "Lazy loading", "pass", f"Few images ({len(images)}) — lazy loading not critical.")

        modern_formats = {"webp", "avif"}
        modern_count = 0
        for img in images:
            src = img.get("src", "").lower().split("?")[0]
            ext = src.rsplit(".", 1)[-1] if "." in src else ""
            if ext in modern_formats:
                modern_count += 1
        modern_pct = round(modern_count / len(images) * 100)
        if modern_pct > 50:
            add(checks, "Images", "Modern formats", "pass", f"{modern_pct}% of images use modern formats (WebP/AVIF).")
        else:
            add(checks, "Images", "Modern formats", "warn", f"Only {modern_pct}% of images use modern formats — consider converting to WebP or AVIF.")

        with_dims = sum(1 for img in images if img.get("width") and img.get("height"))
        if with_dims == len(images):
            add(checks, "Images", "Dimensions defined", "pass", "All images have width and height attributes (prevents layout shift).")
        else:
            missing_dims = len(images) - with_dims
            add(checks, "Images", "Dimensions defined", "warn", f"{missing_dims} image(s) missing width/height attributes — add them to prevent layout shift.")
    else:
        add(checks, "Images", "Image alt attributes", "pass", "No images to check.")
    return checks


def check_links(links, parsed_url):
    checks = []
    internal = sum(1 for l in links if urlparse(l["href"]).netloc in ("", parsed_url.netloc))
    external = len(links) - internal
    if links:
        add(checks, "Links", "Internal/external ratio", "pass" if internal > 0 else "warn",
            f"{internal} internal, {external} external links.")
    else:
        add(checks, "Links", "Internal/external ratio", "warn", "No links found on this page.")

    empty_anchor = sum(1 for l in links if not l["text"].strip())
    if empty_anchor == 0:
        add(checks, "Links", "Anchor text", "pass", "All links have descriptive anchor text.")
    else:
        add(checks, "Links", "Anchor text", "warn", f"{empty_anchor} link(s) without anchor text — add descriptive text for better SEO.")
    return checks


def check_open_graph(meta_names):
    checks = []
    og_title = meta_names.get("og:title", "")
    og_desc = meta_names.get("og:description", "")
    og_image = meta_names.get("og:image", "")
    og_count = sum(1 for v in [og_title, og_desc, og_image] if v)
    if og_count == 3:
        add(checks, "Open Graph", "OG tags", "pass", "og:title, og:description, og:image are all present.")
    elif og_count > 0:
        missing_og = [t for t, v in [("og:title", og_title), ("og:description", og_desc), ("og:image", og_image)] if not v]
        add(checks, "Open Graph", "OG tags", "warn", f"Missing: {', '.join(missing_og)}.")
    else:
        add(checks, "Open Graph", "OG tags", "fail", "No Open Graph tags — add og:title, og:description, og:image for social sharing.")

    twitter_card = meta_names.get("twitter:card", "")
    if twitter_card:
        add(checks, "Open Graph", "Twitter Card", "pass", f"Twitter Card is set ({twitter_card}).")
    else:
        add(checks, "Open Graph", "Twitter Card", "warn", "No Twitter Card meta — add twitter:card for better Twitter previews.")
    return checks


def check_technical(page, url, canonical, lang, viewport):
    checks = []
    if canonical:
        add(checks, "Technical", "Canonical URL", "pass", f"Canonical is set: {canonical}")
        if canonical.rstrip("/") == url.rstrip("/"):
            add(checks, "Technical", "Canonical match", "pass", "Canonical URL matches the page URL.")
        else:
            add(checks, "Technical", "Canonical match", "warn", f"Canonical URL differs from page URL — verify this is intentional.")
    else:
        add(checks, "Technical", "Canonical URL", "warn", "No canonical URL — add one to prevent duplicate content issues.")

    if lang:
        add(checks, "Technical", "Language", "pass", f"Language attribute is set ({lang}).")
    else:
        add(checks, "Technical", "Language", "warn", "No lang attribute on <html> — add it for accessibility and SEO.")

    if viewport:
        add(checks, "Technical", "Viewport", "pass", "Viewport meta tag is defined.")
    else:
        add(checks, "Technical", "Viewport", "fail", "No viewport meta — add it for mobile responsiveness.")

    hreflangs = page.css("link[rel=alternate][hreflang]")
    if hreflangs:
        langs = [el.attrib.get("hreflang", "") for el in hreflangs]
        add(checks, "Technical", "Hreflang", "pass", f"Hreflang tags found for: {', '.join(langs[:5])}{'...' if len(langs) > 5 else ''}.")
    else:
        add(checks, "Technical", "Hreflang", "pass", "No hreflang tags — single-language site (not required).")

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

    if structured_data_count > 0:
        types_str = ", ".join(ld_types) if ld_types else "detected"
        add(checks, "Technical", "Structured data", "pass", f"{structured_data_count} JSON-LD block(s) found ({types_str}).")
    else:
        add(checks, "Technical", "Structured data", "warn", "No JSON-LD structured data — consider adding Schema.org markup for rich results.")

    return checks, structured_data_count, ld_types


def check_content(page):
    checks = []
    body = page.css("body")
    text = ""
    if body:
        text = " ".join(body.css("::text").getall())
    text = re.sub(r'\s+', ' ', text).strip()
    word_count = len(text.split()) if text else 0

    if word_count >= 300:
        add(checks, "Content", "Word count", "pass", f"{word_count} words on the page (good for SEO).")
    elif word_count >= 100:
        add(checks, "Content", "Word count", "warn", f"Only {word_count} words — consider adding more content (aim for 300+).")
    else:
        add(checks, "Content", "Word count", "fail", f"Only {word_count} words — thin content may hurt rankings (aim for 300+).")

    html_len = len(page.html_content or "")
    text_len = len(text)
    ratio = round(text_len / html_len * 100, 1) if html_len > 0 else 0
    if ratio >= 25:
        add(checks, "Content", "Text-to-HTML ratio", "pass", f"Text-to-HTML ratio is {ratio}% (good).")
    elif ratio >= 10:
        add(checks, "Content", "Text-to-HTML ratio", "warn", f"Text-to-HTML ratio is {ratio}% — consider reducing HTML bloat (aim for 25%+).")
    else:
        add(checks, "Content", "Text-to-HTML ratio", "fail", f"Text-to-HTML ratio is {ratio}% — very low, page may be too heavy on code vs content.")

    return checks, {"word_count": word_count, "text_html_ratio": ratio}


def check_structured_data(page):
    checks = []
    ld_json_elements = page.css('script[type="application/ld+json"]')
    for el in ld_json_elements:
        try:
            content = el.css("::text").get("")
            parsed = json.loads(content)
            items = [parsed] if isinstance(parsed, dict) else parsed if isinstance(parsed, list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                has_type = "@type" in item
                has_name = "name" in item or "headline" in item
                if has_type and has_name:
                    add(checks, "Structured Data", "JSON-LD validation", "pass", f"JSON-LD \"{item.get('@type', '')}\" has required fields.")
                elif has_type:
                    add(checks, "Structured Data", "JSON-LD validation", "warn", f"JSON-LD \"{item.get('@type', '')}\" is missing name/headline field.")
                else:
                    add(checks, "Structured Data", "JSON-LD validation", "warn", "JSON-LD block missing @type field.")
        except (json.JSONDecodeError, TypeError):
            add(checks, "Structured Data", "JSON-LD validation", "warn", "Invalid JSON in JSON-LD block.")

    if not ld_json_elements:
        add(checks, "Structured Data", "JSON-LD validation", "warn", "No JSON-LD blocks to validate.")

    microdata = page.css("[itemscope]")
    if microdata:
        types = [el.attrib.get("itemtype", "unknown") for el in microdata[:5]]
        add(checks, "Structured Data", "Microdata", "pass", f"Microdata found: {', '.join(types)}.")
    else:
        add(checks, "Structured Data", "Microdata", "pass", "No microdata found (JSON-LD is the preferred format).")

    return checks


def check_performance(page):
    checks = []
    scripts = page.css("script[src]")
    blocking = []
    for s in scripts:
        if not s.attrib.get("async") and not s.attrib.get("defer") and not s.attrib.get("type") == "module":
            blocking.append(s.attrib.get("src", ""))
    count = len(blocking)
    if count == 0:
        add(checks, "Performance", "Render-blocking scripts", "pass", "No render-blocking scripts found.")
    elif count <= 3:
        add(checks, "Performance", "Render-blocking scripts", "warn", f"{count} render-blocking script(s) — consider adding async or defer.")
    else:
        add(checks, "Performance", "Render-blocking scripts", "fail", f"{count} render-blocking scripts — add async/defer to improve page load.")

    return checks, {"blocking_scripts": count, "stylesheets": len(page.css("link[rel=stylesheet]")), "lazy_images": sum(1 for img in page.css("img") if img.attrib.get("loading") == "lazy")}


def check_security(url, headers):
    checks = []
    if url.startswith("https://"):
        add(checks, "Security", "HTTPS", "pass", "Page is served over HTTPS.")
    else:
        add(checks, "Security", "HTTPS", "fail", "Page is not served over HTTPS — migrate to HTTPS for security and SEO.")

    security_headers_found = {}
    wanted = {"strict-transport-security": "HSTS", "x-content-type-options": "X-Content-Type-Options", "x-frame-options": "X-Frame-Options"}
    for header_key, label in wanted.items():
        val = headers.get(header_key)
        if val:
            security_headers_found[label] = True

    found_count = len(security_headers_found)
    if found_count == len(wanted):
        add(checks, "Security", "Security headers", "pass", f"All security headers present ({', '.join(security_headers_found.keys())}).")
    elif found_count > 0:
        present = ", ".join(security_headers_found.keys())
        missing = ", ".join(label for label in wanted.values() if label not in security_headers_found)
        add(checks, "Security", "Security headers", "warn", f"Partial security headers ({present}). Missing: {missing}.")
    else:
        add(checks, "Security", "Security headers", "fail", "No security headers found — add HSTS, X-Content-Type-Options, X-Frame-Options.")

    https = url.startswith("https://")
    sec_data = {"https": https, "hsts": "HSTS" in security_headers_found, "x_content_type": "X-Content-Type-Options" in security_headers_found, "x_frame": "X-Frame-Options" in security_headers_found}
    return checks, sec_data


def check_accessibility(page):
    checks = []
    main = page.css("main")
    if main:
        add(checks, "Accessibility", "ARIA landmarks", "pass", "<main> landmark found — good for screen readers.")
    else:
        add(checks, "Accessibility", "ARIA landmarks", "warn", "No <main> landmark — add one to improve accessibility.")
    return checks


def check_social(links):
    checks = []
    social_domains = {
        "linkedin": "linkedin.com",
        "twitter": "twitter.com",
        "facebook": "facebook.com",
        "instagram": "instagram.com",
        "youtube": "youtube.com",
        "github": "github.com",
        "tiktok": "tiktok.com",
        "x": "x.com",
    }
    found = {}
    for l in links:
        href = l["href"].lower()
        for name, domain in social_domains.items():
            if domain in href:
                found[name] = l["href"]

    if "x" in found and "twitter" not in found:
        found["twitter"] = found.pop("x")
    elif "x" in found:
        found.pop("x")

    count = len(found)
    if count >= 2:
        names = ", ".join(found.keys())
        add(checks, "Social", "Social media links", "pass", f"Found {count} social links ({names}).")
    elif count == 1:
        names = ", ".join(found.keys())
        add(checks, "Social", "Social media links", "warn", f"Only 1 social link ({names}) — consider adding more.")
    else:
        add(checks, "Social", "Social media links", "warn", "No social media links detected.")

    return checks, found


def check_feeds(page):
    checks = []
    rss = page.css("link[type='application/rss+xml'], link[type='application/atom+xml']")
    if rss:
        titles = [el.attrib.get("title", el.attrib.get("href", "")) for el in rss]
        add(checks, "Feeds", "RSS/Atom feed", "pass", f"Feed(s) detected: {', '.join(titles[:3])}.")
    else:
        add(checks, "Feeds", "RSS/Atom feed", "warn", "No RSS/Atom feed found — consider adding one for subscribers.")
    return checks


def check_robots_txt(origin):
    checks = []
    robots_url = f"{origin}/robots.txt"
    robots_page = fetch_resource(robots_url)
    robots_text = ""

    if robots_page:
        robots_text = robots_page.css("::text").get("") if robots_page else ""
        if not robots_text:
            robots_text = robots_page.html_content or ""
        add(checks, "Crawlability", "robots.txt present", "pass", f"robots.txt found at {robots_url}.")
    else:
        add(checks, "Crawlability", "robots.txt present", "fail", f"No robots.txt at {robots_url} — create one to guide crawlers.")
        return checks, {"found": False, "sitemaps": [], "blocks_all": False}

    blocks_all = False
    lines = robots_text.split("\n")
    current_agent = None
    for line in lines:
        line_stripped = line.strip().lower()
        if line_stripped.startswith("user-agent:"):
            current_agent = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("disallow:") and current_agent == "*":
            path = line_stripped.split(":", 1)[1].strip()
            if path == "/":
                blocks_all = True

    if blocks_all:
        add(checks, "Crawlability", "robots.txt valid", "warn", "robots.txt blocks all crawlers (Disallow: / for *) — verify this is intentional.")
    else:
        add(checks, "Crawlability", "robots.txt valid", "pass", "robots.txt does not block all crawlers.")

    sitemaps = []
    for line in lines:
        if line.strip().lower().startswith("sitemap:"):
            sitemaps.append(line.strip().split(":", 1)[1].strip())

    if sitemaps:
        add(checks, "Crawlability", "Sitemap in robots.txt", "pass", f"Sitemap directive(s) found: {', '.join(sitemaps[:3])}.")
    else:
        add(checks, "Crawlability", "Sitemap in robots.txt", "warn", "No Sitemap directive in robots.txt — add one to help crawlers.")

    return checks, {"found": True, "sitemaps": sitemaps, "blocks_all": blocks_all}


def check_sitemap(origin, robots_data, links):
    checks = []
    sitemap_url = robots_data["sitemaps"][0] if robots_data.get("sitemaps") else f"{origin}/sitemap.xml"
    sitemap_page = fetch_resource(sitemap_url)

    url_count = 0
    most_recent = None

    if sitemap_page:
        add(checks, "Sitemap", "XML Sitemap accessible", "pass", f"Sitemap found at {sitemap_url}.")
        sitemap_text = sitemap_page.html_content or ""
        url_count = sitemap_text.count("<loc>")

        if url_count > 0 and url_count < 50000:
            add(checks, "Sitemap", "URL count", "pass", f"Sitemap contains {url_count} URLs.")
        elif url_count >= 50000:
            add(checks, "Sitemap", "URL count", "warn", f"Sitemap contains {url_count} URLs — consider splitting (limit is 50,000).")
        else:
            add(checks, "Sitemap", "URL count", "warn", "Sitemap appears empty — add URLs to it.")

        lastmod_text = " ".join(re.findall(r'<lastmod>([^<]+)</lastmod>', sitemap_text))
        dates = _parse_dates_from_text(lastmod_text)
        if dates:
            most_recent = max(dates)
            days_ago = (datetime.now(timezone.utc).replace(tzinfo=None) - most_recent).days
            if days_ago < 30:
                add(checks, "Sitemap", "Freshness", "pass", f"Sitemap last updated {days_ago} days ago.")
            elif days_ago < 90:
                add(checks, "Sitemap", "Freshness", "warn", f"Sitemap last updated {days_ago} days ago — consider updating more frequently.")
            else:
                add(checks, "Sitemap", "Freshness", "fail", f"Sitemap last updated {days_ago} days ago — appears stale.")
        else:
            add(checks, "Sitemap", "Freshness", "warn", "No lastmod dates in sitemap — add them for crawler hints.")
    else:
        add(checks, "Sitemap", "XML Sitemap accessible", "fail", f"No sitemap at {sitemap_url}.")

    html_sitemap = any("/sitemap" in l["href"].lower() and "xml" not in l["href"].lower() for l in links)
    if html_sitemap:
        add(checks, "Sitemap", "HTML Sitemap", "pass", "HTML sitemap link detected on page.")
    else:
        add(checks, "Sitemap", "HTML Sitemap", "warn", "No HTML sitemap link found — consider adding one for users and crawlers.")

    sitemap_data = {"found": sitemap_page is not None, "url_count": url_count, "most_recent_lastmod": most_recent.strftime("%Y-%m-%d") if most_recent else None}
    return checks, sitemap_data


def check_blog(links, origin):
    checks = []
    blog_url = None
    blog_patterns = ["/blog", "/articles", "/news", "/posts", "/journal", "/actualites"]

    for l in links:
        href = l["href"].lower()
        for pattern in blog_patterns:
            if pattern in href:
                blog_url = l["href"]
                break
        if blog_url:
            break

    if blog_url:
        add(checks, "Blog", "Blog presence", "pass", f"Blog section detected: {blog_url}")
        if not blog_url.startswith("http"):
            blog_url = urljoin(origin, blog_url)
        blog_page = fetch_resource(blog_url)
        if blog_page:
            time_tags = blog_page.css("time::attr(datetime)")
            date_source = " ".join(time_tags.getall()) if time_tags else (blog_page.html_content or "")
            dates = _parse_dates_from_text(date_source)

            if dates:
                most_recent = max(dates)
                days_ago = (datetime.now(timezone.utc).replace(tzinfo=None) - most_recent).days
                if days_ago < 30:
                    add(checks, "Blog", "Blog freshness", "pass", f"Most recent blog content is {days_ago} days old.")
                elif days_ago < 90:
                    add(checks, "Blog", "Blog freshness", "warn", f"Most recent blog content is {days_ago} days old — consider publishing more often.")
                else:
                    add(checks, "Blog", "Blog freshness", "fail", f"Most recent blog content is {days_ago} days old — blog appears inactive.")
                return checks, {"found": True, "url": blog_url, "most_recent_date": most_recent.strftime("%Y-%m-%d")}
            add(checks, "Blog", "Blog freshness", "warn", "Could not determine blog freshness — no dates found.")
            return checks, {"found": True, "url": blog_url, "most_recent_date": None}
        else:
            add(checks, "Blog", "Blog freshness", "warn", "Blog page could not be fetched for freshness check.")
            return checks, {"found": True, "url": blog_url, "most_recent_date": None}
    else:
        add(checks, "Blog", "Blog presence", "warn", "No blog or articles section detected — consider starting one for content marketing.")
        return checks, {"found": False, "url": None, "most_recent_date": None}


def analyze_seo(data: dict, page, headers: dict) -> dict:
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

    h1_count = sum(1 for h in headings if h["level"] == 1)
    meta_names = {m["name"].lower(): m["content"] for m in metas}
    parsed_url = urlparse(url)
    origin = f"{parsed_url.scheme}://{parsed_url.netloc}"

    all_checks = []

    all_checks.extend(check_title(title))
    all_checks.extend(check_meta_description(meta_desc))

    content_checks, content_stats = check_content(page)
    all_checks.extend(content_checks)

    all_checks.extend(check_headings(headings))
    all_checks.extend(check_images(images, page))
    all_checks.extend(check_links(links, parsed_url))
    all_checks.extend(check_open_graph(meta_names))

    social_checks, social_links = check_social(links)
    all_checks.extend(social_checks)

    technical_checks, structured_data_count, ld_types = check_technical(page, url, canonical, lang, viewport)
    all_checks.extend(technical_checks)

    all_checks.extend(check_structured_data(page))

    performance_checks, performance_data = check_performance(page)
    all_checks.extend(performance_checks)

    all_checks.extend(check_accessibility(page))

    security_checks, security_data = check_security(url, headers)
    all_checks.extend(security_checks)

    all_checks.extend(check_feeds(page))

    robots_checks, robots_data = check_robots_txt(origin)
    all_checks.extend(robots_checks)

    sitemap_checks, sitemap_data = check_sitemap(origin, robots_data, links)
    all_checks.extend(sitemap_checks)

    blog_checks, blog_data = check_blog(links, origin)
    all_checks.extend(blog_checks)

    max_score = len(all_checks) * 2
    raw_score = sum(2 if c["status"] == "pass" else 1 if c["status"] == "warn" else 0 for c in all_checks)
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
        "checks": all_checks,
        "content_stats": content_stats,
        "robots_txt": robots_data,
        "sitemap": sitemap_data,
        "blog": blog_data,
        "security_headers": security_data,
        "social_links": social_links,
        "performance": performance_data,
    }


def scrape_url(url: str) -> dict:
    start = time.time()
    page = Fetcher.get(url, stealthy_headers=True)
    elapsed = round(time.time() - start, 2)

    headers = {}
    if hasattr(page, 'headers') and page.headers:
        headers = {k.lower(): v for k, v in page.headers.items()}

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
            "width": img.attrib.get("width", ""),
            "height": img.attrib.get("height", ""),
            "loading": img.attrib.get("loading", ""),
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

    data["seo"] = analyze_seo(data, page, headers)

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
