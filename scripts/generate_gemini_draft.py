#!/usr/bin/env python3
"""Generate a non-public Japanese editorial draft from an official Microsoft page.

Manual GitHub Actions workflow only. No site modifications, commits, or deployment.
"""
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

SOURCE = "https://learn.microsoft.com/en-us/microsoft-365/copilot/release-notes"
MODEL_PREFERENCE = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash")

class SourceText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.tag = None
        self.buf = []
        self.blocks = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer"):
            self.skip += 1
        if not self.skip and tag in ("h2", "h3", "p", "li"):
            self.tag = tag
            self.buf = []
    def handle_endtag(self, tag):
        if not self.skip and self.tag == tag:
            value = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if 20 <= len(value) <= 1000:
                self.blocks.append({"type": tag, "text": value})
            self.tag = None
        if tag in ("script", "style", "nav", "footer") and self.skip:
            self.skip -= 1
    def handle_data(self, data):
        if self.tag and not self.skip:
            self.buf.append(data)

def request_json(url, data):
    req = urllib.request.Request(
        url, data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "CopilotWeeklyDraft/1.0", "x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        method="POST")
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.load(response)

def main():
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY is missing; no content was published.")
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "CopilotWeeklyDraft/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("Microsoft source unavailable")
        html = response.read(1800000).decode("utf-8", "replace")
    parser = SourceText()
    parser.feed(html)
    blocks = parser.blocks[:120]
    if len(blocks) < 8:
        raise RuntimeError("Source parsing yielded too few blocks; stop.")
    evidence = json.dumps(blocks, ensure_ascii=False)[:35000]
    instructions = (
        "あなたはMicrosoft 365 Copilotの慎重な日本語編集者です。以下はMicrosoft公式リリースノートの抜粋です。"
        "抜粋に明記されている内容のみ使用し、未確認情報を補わないでください。"
        "JSONオブジェクトのみ返してください。構造: "
        "{\"news\":[{\"title\":文字列,\"summary\":文字列,\"evidence_quote\":文字列,"
        "\"announcement_date\":文字列,\"availability\":文字列,\"license\":文字列,"
        "\"source_url\":文字列,\"verified\":false}],"
        "\"practice\":{\"title\":文字列,\"intro\":文字列,\"prompt\":文字列,"
        "\"verification_note\":文字列}}。"
        "newsは最大3件。各evidence_quoteは抜粋内の完全一致の短い原文（40文字以上）とする。"
        "announcement_date、availability、licenseが不明なら必ず「未確認」と記載する。"
        "source_urlは必ず指定のMicrosoft公式URLのみ。verifiedは必ずfalse。"
        "ニュースは事実と利用の提案を区別する。practiceは架空の会議メモなど"
        "実在の顧客・社員・機密情報を含まないCopilot Chat用の練習例にする。"
        "実機検証済み、全ユーザーに提供済み等とは書かない。"
        "候補が不十分ならnewsを空配列にする。"
    )
    payload = {"systemInstruction": {"parts": [{"text": instructions}]},
               "contents": [{"parts": [{"text": "公式URL: " + SOURCE + "\n公式ページの抜粋:\n" + evidence}]}],
               "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    # Discover available models for this key instead of assuming a model exists.
    models_req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": key, "User-Agent": "CopilotWeeklyDraft/1.0"})
    try:
        with urllib.request.urlopen(models_req, timeout=30) as models_response:
            model_data = json.load(models_response)
    except urllib.error.HTTPError as exc:
        print(f"Gemini model discovery returned HTTP {exc.code}; no files published.")
        raise SystemExit(1)
    available = {
        item["name"].split("/")[-1]
        for item in model_data.get("models", [])
        if "generateContent" in item.get("supportedGenerationMethods", [])
    }
    selected = next((name for name in MODEL_PREFERENCE if name in available), None)
    if not selected:
        print("No preferred Gemini model is available to this API key. "
              "Check Google AI Studio models; no files published.")
        print("Available text generation models:", ", ".join(sorted(available)[:25]))
        raise SystemExit(1)
    print("Selected Gemini model:", selected)
    try:
        response = request_json(
            "https://generativelanguage.googleapis.com/v1beta/models/" + selected + ":generateContent",
            payload,
        )
    except urllib.error.HTTPError as exc:
        # Never print the API key, request URL, headers, or full response.
        try:
            err = json.loads(exc.read(12000).decode("utf-8", "replace"))
            detail = err.get("error", {})
            code = detail.get("status", "UNKNOWN")
            message = detail.get("message", "No details returned")
            # Suppress any accidental credentials or URLs in provider text.
            message = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED_KEY]", message)
            message = re.sub(r"https?://\\S+", "[REDACTED_URL]", message)
            print(f"Gemini generation HTTP {exc.code}, status {code}: {message[:600]}")
        except Exception:
            print(f"Gemini generation HTTP {exc.code}, response unreadable.")
        print("No site files were published.")
        raise SystemExit(1)
    parts = response.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    raw = "".join(p.get("text", "") for p in parts)
    draft = json.loads(raw)
    if not isinstance(draft.get("news"), list) or len(draft["news"]) > 3:
        raise ValueError("Unexpected news format")
    evidence_text = " ".join(x["text"] for x in blocks)
    for item in draft["news"]:
        if item.get("source_url") != SOURCE or item.get("verified") is not False:
            raise ValueError("Source or verification status mismatch")
        if not isinstance(item.get("evidence_quote"), str) or item["evidence_quote"] not in evidence_text:
            raise ValueError("News evidence not found in source; reject draft")
        for field in ("title", "summary", "announcement_date", "availability", "license"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError("Missing field: " + field)
    if not isinstance(draft.get("practice"), dict):
        raise ValueError("Missing practice article")
    for field in ("title", "intro", "prompt", "verification_note"):
        if not isinstance(draft["practice"].get(field), str) or not draft["practice"][field].strip():
            raise ValueError("Missing practice field: " + field)
    output = {
        "status": "DRAFT_ONLY_NOT_FACT_CHECKED_NOT_PUBLISHED",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_url": SOURCE, "model": selected,
        "notice": "AI-generated; source quotes are checked but all claims, dates, availability and licenses require independent review.",
        "draft": draft
    }
    Path("copilot-weekly-draft.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Draft generated: {len(draft['news'])} news items and one practice item. No site files changed.")

if __name__ == "__main__":
    main()
