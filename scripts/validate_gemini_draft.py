#!/usr/bin/env python3
"""Conservative quality gate for Gemini-generated Copilot Weekly drafts.

This is a DRAFT gate, not independent fact-checking or approval to publish.
No website files are written.
"""
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import urlparse

INPUT = Path("copilot-weekly-draft.json")
REPORT = Path("copilot-weekly-quality-report.json")
SOURCE = "https://learn.microsoft.com/en-us/microsoft-365/copilot/release-notes"

def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    draft = data.get("draft", {})
    news = draft.get("news", [])
    practice = draft.get("practice", {})
    failures, warnings = [], []
    if data.get("status") != "DRAFT_ONLY_NOT_FACT_CHECKED_NOT_PUBLISHED":
        failures.append("Missing draft-only status")
    if not isinstance(news, list) or len(news) > 3:
        failures.append("News count exceeds 3 or is not a list")
        news = []
    if not news:
        warnings.append("No eligible news; no new news should be published")
    for i, item in enumerate(news, 1):
        prefix = f"news[{i}]"
        if not isinstance(item, dict):
            failures.append(prefix + ": invalid object")
            continue
        if item.get("source_url") != SOURCE:
            failures.append(prefix + ": source URL not allowlisted")
        if item.get("verified") is not False:
            failures.append(prefix + ": falsely marked verified")
        for field in ("title", "summary", "evidence_quote", "announcement_date", "availability", "license"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                failures.append(prefix + ": missing " + field)
        quote = item.get("evidence_quote", "")
        if isinstance(quote, str) and len(quote) < 40:
            failures.append(prefix + ": evidence quote too short")
        for field in ("announcement_date", "availability", "license"):
            value = item.get(field, "")
            if isinstance(value, str) and ("未確認" in value or "不明" in value):
                warnings.append(prefix + ": " + field + " requires independent confirmation")
        date = item.get("announcement_date", "")
        if isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            try:
                d = dt.date.fromisoformat(date)
                if d > dt.datetime.now(dt.timezone.utc).date():
                    failures.append(prefix + ": announcement date in future")
            except ValueError:
                failures.append(prefix + ": invalid date")
        else:
            warnings.append(prefix + ": announcement date is not a verified ISO date")
        warnings.append(prefix + ": claim accuracy and availability NOT independently fact-checked")
    if not isinstance(practice, dict):
        failures.append("Missing practice object")
    else:
        for field in ("title", "intro", "prompt", "verification_note"):
            if not isinstance(practice.get(field), str) or not practice[field].strip():
                failures.append("Practice missing " + field)
        warnings.append("Practice prompt must be checked for fictitious data and untested behavior")
    report = {
        "status": "DRAFT_REJECTED" if failures else "DRAFT_FORMAT_OK_EDITORIAL_REVIEW_REQUIRED",
        "news_count": len(news),
        "practice_count": 1 if isinstance(practice, dict) else 0,
        "failures": failures,
        "warnings": warnings,
        "independent_fact_check": False,
        "approved_for_publication": False,
        "site_modified": False
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Quality gate:", report["status"])
    print("News:", len(news), "Practice:", report["practice_count"],
          "Warnings:", len(warnings), "Failures:", len(failures))
    for failure in failures:
        print("REJECT:", failure)
    print("This test does NOT approve or publish articles.")
    if failures:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
