#!/usr/bin/env python3
"""Build a daily US tech stock news digest and push it to a WeCom group bot.

The script is safe before secrets are configured: without WECHAT_WEBHOOK it
prints the prepared payload and exits successfully.
"""

from __future__ import annotations

import argparse
import email.utils
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports" / "news"
DEFAULT_LOOKBACK_HOURS = 30

DEFAULT_RSS_URLS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL,MSFT,NVDA,GOOGL,AMZN,META,TSLA,AMD,AVGO,ORCL,PLTR,CRWD,NET,ARM,SMCI&region=US&lang=en-US",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19854910",
    "https://www.theverge.com/rss/index.xml",
    "https://techcrunch.com/feed/",
]

TICKER_TERMS = {
    "NVDA": ["nvidia", "nvda", "blackwell", "gpu", "cuda"],
    "MSFT": ["microsoft", "msft", "azure", "copilot", "openai"],
    "AAPL": ["apple", "aapl", "iphone", "mac", "app store"],
    "GOOGL": ["alphabet", "google", "googl", "gemini", "youtube"],
    "AMZN": ["amazon", "amzn", "aws", "anthropic"],
    "META": ["meta", "facebook", "instagram", "whatsapp", "llama"],
    "TSLA": ["tesla", "tsla", "robotaxi", "ev"],
    "AMD": ["amd", "instinct", "mi300", "mi350"],
    "AVGO": ["broadcom", "avgo", "vmware"],
    "ORCL": ["oracle", "orcl"],
    "PLTR": ["palantir", "pltr"],
    "CRWD": ["crowdstrike", "crwd"],
    "NET": ["cloudflare", "net"],
    "ARM": ["arm holdings", "arm"],
    "SMCI": ["super micro", "supermicro", "smci"],
    "TSM": ["tsmc", "taiwan semiconductor", "tsm"],
}

MARKET_TERMS = [
    "stock",
    "stocks",
    "shares",
    "nasdaq",
    "earnings",
    "revenue",
    "guidance",
    "analyst",
    "downgrade",
    "upgrade",
    "price target",
    "market cap",
    "ipo",
    "sec",
    "antitrust",
    "chip",
    "semiconductor",
    "ai",
    "artificial intelligence",
    "cloud",
]

SAMPLE_ITEMS = [
    {
        "title": "Nvidia shares rise as cloud providers expand AI infrastructure spending",
        "summary": "Large cloud customers are expected to keep buying advanced AI accelerators, keeping investor focus on supply and margin trends.",
        "link": "https://example.com/nvidia-ai-cloud",
        "source": "Sample Finance",
        "published": "2026-07-05T12:00:00+00:00",
    },
    {
        "title": "Microsoft investors watch Azure AI growth and capital spending guidance",
        "summary": "Analysts are focused on whether Azure's AI demand can offset higher data-center investment.",
        "link": "https://example.com/microsoft-azure-ai",
        "source": "Sample Markets",
        "published": "2026-07-05T11:00:00+00:00",
    },
    {
        "title": "Apple prepares software updates as AI features remain in focus",
        "summary": "The company continues to face investor questions about device upgrade cycles and AI product timing.",
        "link": "https://example.com/apple-ai-software",
        "source": "Sample Tech",
        "published": "2026-07-05T10:00:00+00:00",
    },
]


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str
    link: str
    source: str
    published: datetime
    tickers: tuple[str, ...]
    score: int


@dataclass(frozen=True)
class AiSummary:
    title: str
    summary: str
    impact: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--max-items", type=int, default=8)
    parser.add_argument("--out", default=str(REPORTS_DIR))
    parser.add_argument("--date", default="", help="Digest date, YYYY-MM-DD. Defaults to today in Asia/Shanghai.")
    parser.add_argument("--rss-url", action="append", default=[], help="Extra RSS/Atom feed URL. Can be repeated.")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending to WeCom.")
    parser.add_argument("--sample", action="store_true", help="Use bundled sample data instead of fetching feeds.")
    parser.add_argument("--no-ai", action="store_true", help="Disable optional LLM Chinese rewrite.")
    return parser.parse_args()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def beijing_today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_source_name(value: str) -> str:
    source = strip_html(value)
    if source.startswith("Yahoo! Finance:"):
        return "Yahoo Finance"
    if "CNBC" in source.upper():
        return "CNBC"
    return source[:48] if source else "Unknown source"


def parse_date(value: str) -> datetime:
    if not value:
        return now_utc()
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return now_utc()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def child_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text.strip()

    for child in node:
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in {name.lower().rsplit("}", 1)[-1] for name in names} and child.text:
            return child.text.strip()
    return ""


def item_link(node: ET.Element) -> str:
    direct = child_text(node, ("link",))
    if direct:
        return direct
    for child in node:
        if child.tag.rsplit("}", 1)[-1].lower() == "link":
            href = child.attrib.get("href", "")
            if href:
                return href
    return ""


def feed_source(root: ET.Element, url: str) -> str:
    channel = root.find("channel")
    title = child_text(channel, ("title",)) if channel is not None else child_text(root, ("title",))
    if title:
        return strip_html(title)
    host = urllib.parse.urlparse(url).netloc.removeprefix("www.")
    return host or "Unknown source"


def parse_feed(xml_bytes: bytes, url: str) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    source = feed_source(root, url)
    nodes = root.findall("./channel/item")
    if not nodes:
        nodes = [node for node in root if node.tag.rsplit("}", 1)[-1].lower() == "entry"]

    entries = []
    for node in nodes:
        title = strip_html(child_text(node, ("title",)))
        summary = strip_html(child_text(node, ("description", "summary", "content", "{http://purl.org/rss/1.0/modules/content/}encoded")))
        link = item_link(node)
        published = child_text(node, ("pubDate", "published", "updated", "dc:date"))
        if title and link:
            entries.append(
                {
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "source": clean_source_name(source),
                    "published": published,
                }
            )
    return entries


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 daily-us-tech-news-bot/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def load_entries(urls: list[str], sample: bool) -> list[dict]:
    if sample:
        return SAMPLE_ITEMS

    entries: list[dict] = []
    errors: list[str] = []
    for url in urls:
        try:
            entries.extend(parse_feed(fetch_url(url), url))
        except (ET.ParseError, urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{url}: {exc}")

    if errors:
        print("Feed warnings:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    return entries


def detect_tickers(text: str) -> tuple[str, ...]:
    lowered = text.lower()
    found = []
    for ticker, terms in TICKER_TERMS.items():
        if any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered) for term in terms):
            found.append(ticker)
    return tuple(found)


def score_entry(entry: dict, cutoff: datetime) -> NewsItem | None:
    published = parse_date(entry.get("published", ""))
    if published < cutoff:
        return None

    title = strip_html(entry.get("title", ""))
    summary = strip_html(entry.get("summary", ""))
    text = f"{title} {summary}"
    tickers = detect_tickers(text)
    lowered = text.lower()
    market_hits = sum(1 for term in MARKET_TERMS if term in lowered)
    score = len(tickers) * 4 + market_hits

    if not tickers and market_hits < 2:
        return None

    return NewsItem(
        title=title,
        summary=summary,
        link=entry.get("link", ""),
        source=clean_source_name(entry.get("source", "Unknown source")),
        published=published,
        tickers=tickers,
        score=score,
    )


def dedupe_and_rank(entries: list[dict], lookback_hours: int, max_items: int) -> list[NewsItem]:
    cutoff = now_utc() - timedelta(hours=lookback_hours)
    seen: set[str] = set()
    items: list[NewsItem] = []
    for entry in entries:
        item = score_entry(entry, cutoff)
        if item is None:
            continue
        key = re.sub(r"[^a-z0-9]+", "", item.title.lower())[:120]
        if key in seen:
            continue
        seen.add(key)
        items.append(item)

    items.sort(key=lambda item: (item.score, item.published), reverse=True)
    return items[:max_items]


def extract_json_array(text: str) -> list[dict]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def call_llm(items: list[NewsItem]) -> dict[str, AiSummary]:
    api_key = os.environ.get("NEWS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {}

    base_url = os.environ.get("NEWS_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("NEWS_LLM_MODEL", "gpt-4o-mini")
    endpoint = f"{base_url}/chat/completions"
    source_items = [
        {
            "id": str(index),
            "title": item.title,
            "summary": item.summary,
            "tickers": item.tickers,
            "source": item.source,
        }
        for index, item in enumerate(items)
    ]
    prompt = (
        "把这些美股科技新闻标题改写成适合企业微信群标题列表的中文。"
        "只返回 JSON 数组，每项包含 id、title_cn。"
        "title_cn 要简洁，保留公司名、股票代码和关键事件，不要添加摘要。"
    )
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是美股科技新闻编辑，输出简洁、准确、中文。"},
            {"role": "user", "content": prompt + "\n\n" + json.dumps(source_items, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        content = body["choices"][0]["message"]["content"]
    except (KeyError, json.JSONDecodeError, urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"LLM warning: {exc}", file=sys.stderr)
        return {}

    summaries: dict[str, AiSummary] = {}
    for row in extract_json_array(content):
        item_id = str(row.get("id", ""))
        if item_id:
            summaries[item_id] = AiSummary(
                title=strip_html(str(row.get("title_cn", ""))),
                summary="",
                impact="",
            )
    return summaries


def build_markdown(
    items: list[NewsItem],
    report_date: str,
    lookback_hours: int,
    ai_summaries: Optional[dict[str, AiSummary]] = None,
) -> str:
    ai_summaries = ai_summaries or {}
    header = [
        f"**美股科技新闻标题 | {report_date}**",
        f"> 最近 {lookback_hours} 小时，聚焦科技股、AI、半导体、云计算和大型平台公司。",
        "",
    ]

    if not items:
        return "\n".join(
            header
            + [
                "未抓取到足够相关的新闻。可能是新闻源暂时不可用，或过去一天科技美股重大新闻较少。",
                "",
                "建议检查 RSS 源或稍后重跑。",
            ]
        )

    overview_tickers = []
    for item in items:
        overview_tickers.extend(item.tickers)
    unique_tickers = []
    for ticker in overview_tickers:
        if ticker not in unique_tickers:
            unique_tickers.append(ticker)

    lines = header + [
        f"**今日关注：** {', '.join(unique_tickers[:10]) if unique_tickers else 'AI、半导体、云计算、平台科技'}",
        "",
    ]

    for index, item in enumerate(items, start=1):
        ai = ai_summaries.get(str(index - 1))
        title = ai.title if ai and ai.title else item.title
        lines.append(f"{index}. [{title}]({item.link})")
    return "\n".join(lines)


def save_report(markdown: str, items: list[NewsItem], out_dir: Path, report_date: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"us_tech_news_{report_date}.md"
    json_path = out_dir / f"us_tech_news_{report_date}.json"
    md_path.write_text(markdown + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            [
                {
                    "title": item.title,
                    "summary": item.summary,
                    "link": item.link,
                    "source": item.source,
                    "published": item.published.isoformat(),
                    "tickers": item.tickers,
                    "score": item.score,
                }
                for item in items
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return md_path, json_path


def post_json(webhook: str, payload: dict, dry_run: bool) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if dry_run or not webhook:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    request = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"WeCom webhook request failed: {exc}") from exc

    result = json.loads(response_body)
    if result.get("errcode") != 0:
        raise RuntimeError(f"WeCom webhook returned error: {response_body}")


def send_markdown(webhook: str, markdown: str, dry_run: bool) -> None:
    payload = {"msgtype": "markdown", "markdown": {"content": markdown[:3900]}}
    post_json(webhook, payload, dry_run)


def main() -> int:
    args = parse_args()
    report_date = args.date or beijing_today()
    urls = DEFAULT_RSS_URLS + args.rss_url

    entries = load_entries(urls, args.sample)
    items = dedupe_and_rank(entries, args.lookback_hours, args.max_items)
    ai_summaries = {} if args.no_ai else call_llm(items)
    markdown = build_markdown(items, report_date, args.lookback_hours, ai_summaries)
    md_path, json_path = save_report(markdown, items, Path(args.out).resolve(), report_date)

    webhook = os.environ.get("WECHAT_WEBHOOK", "").strip()
    dry_run = args.dry_run or not webhook
    send_markdown(webhook, markdown, dry_run)

    mode = "dry-run" if dry_run else "sent"
    print(f"{mode}: {md_path.relative_to(ROOT)}")
    print(f"saved: {json_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
