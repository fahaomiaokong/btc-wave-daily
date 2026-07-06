#!/usr/bin/env python3
"""Build a daily US sector performance digest and push it to a WeCom group bot."""

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
REPORTS_DIR = ROOT / "reports" / "sectors"
DEFAULT_LOOKBACK_HOURS = 30

SECTOR_ETFS = {
    "XLK": "科技",
    "XLC": "通信服务",
    "XLY": "可选消费",
    "XLP": "必选消费",
    "XLF": "金融",
    "XLV": "医疗保健",
    "XLI": "工业",
    "XLE": "能源",
    "XLB": "材料",
    "XLRE": "房地产",
    "XLU": "公用事业",
}

MARKET_RSS_URLS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,DIA,IWM,XLK,XLC,XLY,XLP,XLF,XLV,XLI,XLE,XLB,XLRE,XLU&region=US&lang=en-US",
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "https://www.marketwatch.com/rss/topstories",
]


@dataclass(frozen=True)
class SectorMove:
    symbol: str
    name: str
    price: float
    previous_close: float
    change_pct: float
    as_of: str


@dataclass(frozen=True)
class NewsEntry:
    title: str
    summary: str
    link: str
    source: str
    published: datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback-hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--top-reasons", type=int, default=5)
    parser.add_argument("--out", default=str(REPORTS_DIR))
    parser.add_argument("--date", default="", help="Report date, YYYY-MM-DD. Defaults to today in Asia/Shanghai.")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without sending to WeCom.")
    parser.add_argument("--sample", action="store_true", help="Use bundled sample data instead of fetching market data.")
    parser.add_argument("--no-ai", action="store_true", help="Disable optional LLM reason generation.")
    return parser.parse_args()


def beijing_today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 daily-us-sector-bot/1.0",
            "Accept": "application/json, application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


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


def child_text(node: Optional[ET.Element], names: tuple[str, ...]) -> str:
    if node is None:
        return ""
    target_names = {name.lower().rsplit("}", 1)[-1] for name in names}
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text.strip()
    for child in node:
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in target_names and child.text:
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
    if title.startswith("Yahoo! Finance:"):
        return "Yahoo Finance"
    if title:
        return strip_html(title)[:48]
    return urllib.parse.urlparse(url).netloc.removeprefix("www.") or "Unknown source"


def parse_feed(xml_bytes: bytes, url: str) -> list[NewsEntry]:
    root = ET.fromstring(xml_bytes)
    source = feed_source(root, url)
    nodes = root.findall("./channel/item")
    if not nodes:
        nodes = [node for node in root if node.tag.rsplit("}", 1)[-1].lower() == "entry"]

    entries: list[NewsEntry] = []
    for node in nodes:
        title = strip_html(child_text(node, ("title",)))
        summary = strip_html(child_text(node, ("description", "summary", "content", "{http://purl.org/rss/1.0/modules/content/}encoded")))
        link = item_link(node)
        published = parse_date(child_text(node, ("pubDate", "published", "updated", "dc:date")))
        if title and link:
            entries.append(NewsEntry(title, summary, link, source, published))
    return entries


def fetch_news(lookback_hours: int) -> list[NewsEntry]:
    cutoff = now_utc() - timedelta(hours=lookback_hours)
    entries: list[NewsEntry] = []
    errors: list[str] = []
    for url in MARKET_RSS_URLS:
        try:
            entries.extend(entry for entry in parse_feed(fetch_url(url), url) if entry.published >= cutoff)
        except (ET.ParseError, urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{url}: {exc}")
    if errors:
        print("News warnings:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    seen: set[str] = set()
    unique: list[NewsEntry] = []
    for entry in sorted(entries, key=lambda item: item.published, reverse=True):
        key = re.sub(r"[^a-z0-9]+", "", entry.title.lower())[:120]
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique[:20]


def fetch_sector_move(symbol: str, name: str) -> SectorMove:
    encoded = urllib.parse.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=10d&interval=1d"
    data = json.loads(fetch_url(url).decode("utf-8"))
    result = data["chart"]["result"][0]
    meta = result["meta"]
    quote = result["indicators"]["quote"][0]
    timestamps = result.get("timestamp", [])
    closes = quote.get("close", [])

    valid = [(ts, close) for ts, close in zip(timestamps, closes) if close is not None]
    if len(valid) < 2:
        raise RuntimeError(f"Not enough close data for {symbol}")

    latest_ts, latest_close = valid[-1]
    _, previous_close = valid[-2]
    regular_price = meta.get("regularMarketPrice")
    price = float(regular_price if regular_price is not None else latest_close)
    previous = float(previous_close)
    change_pct = ((price / previous) - 1.0) * 100.0
    as_of = datetime.fromtimestamp(latest_ts, tz=timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    return SectorMove(symbol, name, price, previous, change_pct, as_of)


def sample_moves() -> list[SectorMove]:
    return [
        SectorMove("XLK", "科技", 259.14, 254.10, 1.98, "2026-07-05"),
        SectorMove("XLE", "能源", 91.20, 92.68, -1.60, "2026-07-05"),
        SectorMove("XLF", "金融", 52.11, 51.72, 0.75, "2026-07-05"),
        SectorMove("XLU", "公用事业", 78.44, 79.05, -0.77, "2026-07-05"),
        SectorMove("XLV", "医疗保健", 148.03, 148.21, -0.12, "2026-07-05"),
    ]


def sample_news() -> list[NewsEntry]:
    now = now_utc()
    return [
        NewsEntry("Technology stocks rise as AI chip demand lifts semiconductor shares", "", "https://example.com/tech-ai", "Sample Markets", now),
        NewsEntry("Oil prices fall after supply concerns ease", "", "https://example.com/oil", "Sample Markets", now),
        NewsEntry("Bank stocks edge higher as yields stabilize", "", "https://example.com/banks", "Sample Markets", now),
    ]


def load_sector_moves(sample: bool) -> list[SectorMove]:
    if sample:
        return sample_moves()
    moves: list[SectorMove] = []
    errors: list[str] = []
    for symbol, name in SECTOR_ETFS.items():
        try:
            moves.append(fetch_sector_move(symbol, name))
        except (KeyError, IndexError, TypeError, ValueError, RuntimeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{symbol}: {exc}")
    if errors:
        print("Market data warnings:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    return sorted(moves, key=lambda move: move.change_pct, reverse=True)


def format_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def reason_fallback(move: SectorMove, news: list[NewsEntry]) -> str:
    text = " ".join(f"{entry.title} {entry.summary}" for entry in news).lower()
    if move.symbol == "XLK" and any(term in text for term in ("ai", "chip", "semiconductor", "nvidia", "microsoft")):
        if move.change_pct >= 0:
            return "AI、芯片和大型科技股相关新闻较多，带动科技板块关注度。"
        return "AI、芯片和大型科技股消息密集，但板块下跌，可能反映大型科技股获利回吐、估值压力或供应链担忧。"
    if move.symbol == "XLE" and any(term in text for term in ("oil", "energy", "crude", "opec")):
        direction = "支撑" if move.change_pct >= 0 else "拖累"
        return f"原油、供需和能源价格相关消息{direction}能源板块表现。"
    if move.symbol == "XLF" and any(term in text for term in ("yield", "rate", "fed", "bank")):
        direction = "支撑" if move.change_pct >= 0 else "压制"
        return f"利率、收益率和银行股消息{direction}金融板块表现。"
    if move.symbol == "XLV" and any(term in text for term in ("drug", "health", "biotech", "pharma")):
        return "医药、医保或生物科技相关新闻影响医疗保健板块。"
    direction = "上涨" if move.change_pct >= 0 else "下跌"
    return f"{move.name}板块{direction}幅度靠前，需结合盘后新闻和隔夜宏观数据继续确认原因。"


def extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def call_llm(moves: list[SectorMove], news: list[NewsEntry], top_reasons: int) -> dict:
    api_key = os.environ.get("NEWS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {}

    base_url = os.environ.get("NEWS_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("NEWS_LLM_MODEL", "gpt-4o-mini")
    endpoint = f"{base_url}/chat/completions"
    top_moves = sorted(moves, key=lambda move: abs(move.change_pct), reverse=True)[:top_reasons]
    payload_data = {
        "sectors": [
            {"symbol": move.symbol, "name": move.name, "change_pct": round(move.change_pct, 2)}
            for move in moves
        ],
        "top_moves": [
            {"symbol": move.symbol, "name": move.name, "change_pct": round(move.change_pct, 2)}
            for move in top_moves
        ],
        "news": [
            {"title": entry.title, "summary": entry.summary, "source": entry.source}
            for entry in news[:15]
        ],
    }
    prompt = (
        "根据美股板块 ETF 涨跌和新闻标题，生成企业微信群用的中文板块日报。"
        "只返回 JSON 对象，字段：overview、reasons。"
        "overview 是一句话概括市场风格。"
        "reasons 是对象，key 为 ETF 代码，value 为一句中文原因。"
        "原因要谨慎使用“可能/主要受/市场关注”，不要编造新闻中没有的信息。"
    )
    request_payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "你是美股市场编辑，输出简洁、准确、中文。"},
            {"role": "user", "content": prompt + "\n\n" + json.dumps(payload_data, ensure_ascii=False)},
        ],
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        content = body["choices"][0]["message"]["content"]
    except (KeyError, json.JSONDecodeError, urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"LLM warning: {exc}", file=sys.stderr)
        return {}
    return extract_json_object(content)


def build_markdown(
    moves: list[SectorMove],
    news: list[NewsEntry],
    report_date: str,
    top_reasons: int,
    ai: Optional[dict] = None,
) -> str:
    ai = ai or {}
    if not moves:
        return "\n".join(
            [
                f"**美股板块涨跌 | {report_date}**",
                "> 未抓取到板块行情数据，建议稍后重跑。",
            ]
        )

    as_of = moves[0].as_of
    top_abs = sorted(moves, key=lambda move: abs(move.change_pct), reverse=True)[:top_reasons]
    overview = ai.get("overview") or "按行业 ETF 观察，美股板块表现出现分化，重点关注涨跌幅靠前板块。"
    reasons = ai.get("reasons") if isinstance(ai.get("reasons"), dict) else {}

    lines = [
        f"**美股板块涨跌 | {report_date}**",
        f"> 行情日期：{as_of}，以 SPDR 行业 ETF 近一交易日表现近似观察。",
        "",
        f"**市场风格：** {overview}",
        "",
        "**板块表现：**",
    ]
    for move in moves:
        lines.append(f"{move.name} {move.symbol}：{format_pct(move.change_pct)}")

    lines.extend(["", "**波动较大原因：**"])
    for move in top_abs:
        reason = str(reasons.get(move.symbol) or reason_fallback(move, news))
        lines.append(f"- {move.name} {move.symbol} {format_pct(move.change_pct)}：{reason}")

    if news:
        lines.extend(["", "**参考新闻：**"])
        for entry in news[:5]:
            lines.append(f"- [{entry.title}]({entry.link})")
    return "\n".join(lines)


def save_report(markdown: str, moves: list[SectorMove], news: list[NewsEntry], out_dir: Path, report_date: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"us_sector_moves_{report_date}.md"
    json_path = out_dir / f"us_sector_moves_{report_date}.json"
    md_path.write_text(markdown + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "moves": [move.__dict__ for move in moves],
                "news": [
                    {
                        "title": entry.title,
                        "summary": entry.summary,
                        "link": entry.link,
                        "source": entry.source,
                        "published": entry.published.isoformat(),
                    }
                    for entry in news
                ],
            },
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
    moves = load_sector_moves(args.sample)
    news = sample_news() if args.sample else fetch_news(args.lookback_hours)
    ai = {} if args.no_ai else call_llm(moves, news, args.top_reasons)
    markdown = build_markdown(moves, news, report_date, args.top_reasons, ai)
    md_path, json_path = save_report(markdown, moves, news, Path(args.out).resolve(), report_date)

    webhook = os.environ.get("WECHAT_WEBHOOK", "").strip()
    dry_run = args.dry_run or not webhook
    send_markdown(webhook, markdown, dry_run)

    mode = "dry-run" if dry_run else "sent"
    print(f"{mode}: {md_path.relative_to(ROOT)}")
    print(f"saved: {json_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
