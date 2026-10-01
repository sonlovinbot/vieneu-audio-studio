"""Extract article text from URLs using trafilatura."""

from urllib.parse import urlparse

import trafilatura


def extract_text_from_url(url: str, max_chars: int = 5000) -> dict:
    """
    Extract article text from a URL.

    Returns dict with keys: title, text, char_count, truncated, error
    """
    # Validate URL
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"title": None, "text": None, "char_count": 0, "truncated": False, "error": "URL must start with http:// or https://"}
        if not parsed.netloc:
            return {"title": None, "text": None, "char_count": 0, "truncated": False, "error": "Invalid URL"}
    except Exception:
        return {"title": None, "text": None, "char_count": 0, "truncated": False, "error": "Invalid URL format"}

    # Fetch and extract
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as e:
        return {"title": None, "text": None, "char_count": 0, "truncated": False, "error": f"Failed to fetch URL: {e}"}

    if not downloaded:
        return {"title": None, "text": None, "char_count": 0, "truncated": False, "error": "Could not fetch the URL (may be unreachable or require login)"}

    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if not text or len(text.strip()) < 20:
        return {"title": None, "text": None, "char_count": 0, "truncated": False, "error": "Could not extract meaningful text from this URL"}

    # Try to get title
    metadata = trafilatura.extract(downloaded, output_format="json", include_comments=False)
    title = None
    if metadata:
        import json
        try:
            meta_dict = json.loads(metadata)
            title = meta_dict.get("title")
        except (json.JSONDecodeError, TypeError):
            pass

    text = text.strip()
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]

    return {
        "title": title,
        "text": text,
        "char_count": len(text),
        "truncated": truncated,
        "error": None,
    }
