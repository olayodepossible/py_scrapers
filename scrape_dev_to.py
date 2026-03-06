"""
Scrape article Q&A content from a DEV.to (or similar) URL
and save to a text file in the output_data.txt file.
Uses only Python standard library (no bs4 required).
"""

import argparse
import re
import urllib.request
from pathlib import Path

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "output_data.txt"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def fetch_page(url: str) -> str:
    """Fetch page HTML."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_article_via_regex(html: str) -> str:
    """
    Extract article body from DEV.to HTML.
    Tries crayons-article__body div first, then falls back to article tag.
    """
    # DEV.to wraps article body in div with class crayons-article__body
    body_match = re.search(
        r'<div[^>]*class="[^"]*crayons-article__body[^"]*"[^>]*>(.*?)</div>\s*</article>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not body_match:
        body_match = re.search(
            r"<article[^>]*>(.*?)</article>",
            html,
            re.DOTALL | re.IGNORECASE,
        )
    if not body_match:
        return ""

    body_html = body_match.group(1)

    # Strip script and style tags and their content
    body_html = re.sub(r"<script[^>]*>.*?</script>", "", body_html, flags=re.DOTALL | re.IGNORECASE)
    body_html = re.sub(r"<style[^>]*>.*?</style>", "", body_html, flags=re.DOTALL | re.IGNORECASE)

    # Extract text from blocks: h1-h6, p, li (preserve order by scanning)
    blocks = []
    pos = 0
    pattern = re.compile(
        r"</?(?:h[1-6]|p|li|strong|ul|ol)[^>]*>",
        re.IGNORECASE,
    )
    while True:
        m = pattern.search(body_html, pos)
        if not m:
            break
        tag = m.group(0)
        start = m.end()
        if tag.startswith("</"):
            pos = start
            continue
        # Find closing tag
        tag_name = re.match(r"<(\w+)", tag, re.I).group(1).lower()
        close = re.compile(rf"</{tag_name}\s*>", re.IGNORECASE)
        end_m = close.search(body_html, start)
        if not end_m:
            pos = start
            continue
        inner = body_html[start : end_m.start()]
        # Remove nested tags for plain text
        inner = re.sub(r"<[^>]+>", " ", inner)
        inner = re.sub(r"&nbsp;", " ", inner)
        inner = re.sub(r"&amp;", "&", inner)
        inner = re.sub(r"&lt;", "<", inner)
        inner = re.sub(r"&gt;", ">", inner)
        inner = re.sub(r"&quot;", '"', inner)
        text = " ".join(inner.split()).strip()
        if text and len(text) > 2:
            blocks.append((tag_name, text))
        pos = end_m.end()
    if not blocks:
        # Fallback: strip all tags and use as one block
        plain = re.sub(r"<[^>]+>", "\n", body_html)
        plain = re.sub(r"\n+", "\n", plain).strip()
        return plain

    # Build output with simple structure
    lines = []
    for tag_name, text in blocks:
        if tag_name in ("h1", "h2", "h3", "h4"):
            lines.append("")
            lines.append(text)
            if tag_name == "h2":
                lines.append("-" * 40)
        elif tag_name == "p" or tag_name == "li":
            lines.append(text)
        elif tag_name == "strong":
            lines.append(text)
    return "\n".join(lines).strip()


def clean_and_format(raw: str) -> str:
    """Clean extracted text and add section separators."""
    # Skip UI/footer lines
    skip_phrases = (
        "log in",
        "create account",
        "report abuse",
        "hide this comment",
        "confirm",
        "code of conduct",
        "subscribe",
        "like comment",
        "comment button",
        "dropdown menu",
        "copy link",
        "top comments",
        "templates let you",
        "some comments may only be visible",
        "sign in to view",
        "hide child comments",
        "for further actions",
    )
    out = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            out.append("")
            continue
        if any(p in line.lower() for p in skip_phrases):
            continue
        if len(line) < 4 and not re.match(r"^\d+\.", line):
            continue
        out.append(line)
    return "\n".join(out).strip()


def scrape_qa_to_text(url: str, output_path: Path) -> None:
    """Fetch page, extract Q&A content, and write to file."""
    html = fetch_page(url)
    text = extract_article_via_regex(html)
    if len(text) < 300:
        # Fallback: look for any large block of text that looks like the article
        for blob in re.findall(r"<article[^>]*>(.*?)</article>", html, re.DOTALL | re.I):
            plain = re.sub(r"<[^>]+>", "\n", blob)
            plain = re.sub(r"\n+", "\n", plain).strip()
            if len(plain) > len(text):
                text = plain
    text = clean_and_format(text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    title = extract_page_title(html) if html else "Scraped article"
    header = f"Source: {url}\nTitle: {title}\n\n"
    output_path.write_text(header + text, encoding="utf-8")
    print(f"Saved {len(text)} characters to {output_path}")


def extract_page_title(html: str) -> str:
    """Extract <title> from HTML, or return default."""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return m.group(1).strip() if m else "Scraped article"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Q&A content from a DEV.to article URL.")
    parser.add_argument("url", help="Article URL to scrape (e.g. https://dev.to/...)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output text file path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    scrape_qa_to_text(args.url, args.output)
