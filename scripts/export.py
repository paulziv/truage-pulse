"""
CLI: export any report as a self-contained HTML file.

  python scripts/export.py audit
  python scripts/export.py audit /path/to/output.html
  python scripts/export.py dictionary
  python scripts/export.py all          # exports all reports to data/exports/

If no path is given, files land in <repo>/data/exports/ with timestamped names.
On the NAS (when running inside the container) data/exports/ is volume-mounted,
so files appear in /volume1/docker/truage-pulse/data/exports/ on the host.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT))

from pulse import audit, daily, dictionary, export  # noqa: E402

EXPORTS_DIR = REPO_ROOT / "data" / "exports"

app = Flask(
    __name__,
    template_folder=str(REPO_ROOT / "templates"),
    static_folder=str(REPO_ROOT / "static"),
)


def export_one(report_name: str, out_path: Path | None = None) -> Path:
    """Render and save a single report. Returns the path written."""
    if report_name == "audit":
        data = audit.build_audit()
        template = "audit.html"
        ctx = {"r": data}
    elif report_name == "daily":
        data = daily.build_daily()
        template = "daily.html"
        ctx = {"d": data}
    elif report_name == "dictionary":
        data = dictionary.build_dictionary()
        template = "dictionary.html"
        ctx = {"d": data}
    else:
        raise SystemExit(f"Unknown report: {report_name}. Try: audit, daily, dictionary, all")

    with app.test_request_context(f"/{report_name}"):
        html = render_template(template, **ctx)
    standalone = export.to_standalone_html(html)

    if out_path is None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = EXPORTS_DIR / export.filename_for(report_name)

    out_path.write_text(standalone, encoding="utf-8")
    return out_path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    report = sys.argv[1]
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if report == "all":
        for r in ["audit", "dictionary", "daily"]:
            path = export_one(r)
            print(f"Wrote {path}")
    else:
        path = export_one(report, out)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
