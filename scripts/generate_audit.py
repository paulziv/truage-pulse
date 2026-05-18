"""
CLI: generate the AM Audit HTML and write to disk for preview without the server.

  python scripts/generate_audit.py [output.html]
"""
import sys
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Reuse the same templates via a throwaway Flask app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pulse import audit  # noqa: E402

app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent.parent / "templates"),
    static_folder=str(Path(__file__).resolve().parent.parent / "static"),
)


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("audit.html")

    report = audit.build_audit()
    with app.test_request_context():
        html = render_template("audit.html", r=report)

    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path} (Hygiene Score: {report.hygiene_score.score})")


if __name__ == "__main__":
    main()
