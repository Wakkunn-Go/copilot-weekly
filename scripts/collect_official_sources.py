#!/usr/bin/env python3
"""Read-only official-source collector. No article publication or AI claims."""
import datetime as dt
import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

URL = "https://learn.microsoft.com/en-us/microsoft-365/copilot/release-notes"

class Headings(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts = []
        self.headings = []
    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3"):
            self.depth = 1
            self.parts = []
        elif self.depth:
            self.depth += 1
    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1
            if self.depth == 0:
                heading = re.sub(r"\s+", " ", "".join(self.parts)).strip()
                if heading:
                    self.headings.append(heading)
    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "CopilotWeeklySourceAudit/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"Official source returned HTTP {response.status}")
        html = response.read(2000000).decode("utf-8", errors="replace")
    parser = Headings()
    parser.feed(html)
    if not parser.headings or "Copilot" not in html:
        raise RuntimeError("Unexpected source format; stop safely.")
    result = {
        "source_url": URL,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "headings": parser.headings[:100],
        "editorial_status": "SOURCE_DISCOVERY_ONLY_NOT_VERIFIED_FOR_PUBLICATION",
        "notes": "Headings are discovery leads, not verified news. Publication dates, license, rollout, claims and source links require separate verification.",
    }
    Path("source-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(result['headings'])} official page headings. No website files changed.")

if __name__ == "__main__":
    main()
