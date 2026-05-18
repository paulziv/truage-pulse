"""
Export reports as self-contained, attachable HTML files.

Takes a rendered template and turns it into a file that works when:
  - Attached to an email
  - Saved to disk
  - Opened from a thumb drive
  - Forwarded to someone outside your network

Strategy:
  1. Render the report normally
  2. Inline the CSS file (no external stylesheet reference)
  3. Strip the top nav (no point in a static file)
  4. Strip "refresh from HubSpot" links and any forms
  5. Add a "Snapshot" banner so recipients know it's static
  6. Return as bytes or write to disk
"""
import re
from pathlib import Path
from datetime import datetime

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _read_css() -> str:
    """Read the shared stylesheet."""
    css_path = STATIC_DIR / "styles.css"
    if not css_path.exists():
        return ""
    return css_path.read_text(encoding="utf-8")


def _inline_css(html: str) -> str:
    """Replace the stylesheet link with an inline <style> block."""
    css = _read_css()
    # Match the Flask-generated url_for output
    pattern = re.compile(
        r'<link\s+rel="stylesheet"\s+href="[^"]*styles\.css"[^>]*>',
        re.IGNORECASE,
    )
    return pattern.sub(f"<style>\n{css}\n</style>", html)


def _strip_topnav(html: str) -> str:
    """Remove the top nav (links won't work in a static file)."""
    return re.sub(
        r'<nav class="topnav">.*?</nav>',
        "",
        html,
        flags=re.DOTALL,
    )


def _strip_refresh_link(html: str) -> str:
    """Remove the 'refresh from HubSpot' link inside the eyebrow."""
    return re.sub(
        r'\s*·\s*<a href="\?fresh=1"[^>]*>refresh from HubSpot</a>',
        "",
        html,
    )


def _strip_forms(html: str) -> str:
    """Remove forms — they post to URLs that don't exist in a static file."""
    return re.sub(r"<form[^>]*>.*?</form>", "", html, flags=re.DOTALL)


def _add_snapshot_banner(html: str) -> str:
    """Add a banner at the top so recipients know the file is a snapshot."""
    timestamp = datetime.utcnow().strftime("%B %d, %Y at %H:%M UTC")
    banner = f"""
<div style="background:#fff4e0;border:1px solid #c77700;color:#7a4500;padding:10px 16px;
            margin:0 0 0 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
            Helvetica,Arial,sans-serif;font-size:13px;text-align:center;">
  📎 <strong>Snapshot</strong> — exported {timestamp}.
  For live data, contact the report owner.
</div>
"""
    # Insert just after <body>
    return re.sub(r"(<body[^>]*>)", r"\1" + banner, html, count=1)


def to_standalone_html(html: str) -> str:
    """Transform a rendered Flask template into a self-contained HTML document."""
    html = _inline_css(html)
    html = _strip_topnav(html)
    html = _strip_refresh_link(html)
    html = _strip_forms(html)
    html = _add_snapshot_banner(html)
    return html


def filename_for(report_name: str) -> str:
    """Produce a filesystem-safe filename for a given report and today's date."""
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", report_name.lower())
    return f"truage-pulse-{safe}-{date_str}.html"
