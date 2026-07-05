#!/usr/bin/env python3
"""Generate the daily BTC wave report and push it to a WeCom group bot.

The script is intentionally safe to run before secrets are configured:
without WECHAT_WEBHOOK it prints the prepared message and exits successfully.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
WAVE_SCRIPT = ROOT / "elliott-wave-us-stock" / "scripts" / "elliott_wave_chart.py"


@dataclass(frozen=True)
class ReportPaths:
    date: str
    chart: Path
    post: Path
    data: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTC-USD", help="Yahoo Finance symbol, default: BTC-USD")
    parser.add_argument("--horizon", default="short", choices=["short", "long", "auto", "listing"])
    parser.add_argument("--interval", default="1d")
    parser.add_argument("--sensitivity", default="0.04", help="BTC short-wave sensitivity that keeps the C-wave count")
    parser.add_argument("--out", default=str(REPORTS_DIR))
    parser.add_argument("--date", default="", help="Report date to read, YYYY-MM-DD. Defaults to generated/latest date.")
    parser.add_argument("--skip-generate", action="store_true", help="Use an existing report instead of running yfinance.")
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without sending to WeCom.")
    parser.add_argument(
        "--send-image",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Send the PNG as a WeCom image message after the markdown message.",
    )
    return parser.parse_args()


def run_wave_script(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(WAVE_SCRIPT),
        args.symbol,
        "--horizon",
        args.horizon,
        "--interval",
        args.interval,
        "--sensitivity",
        args.sensitivity,
        "--out",
        args.out,
    ]
    subprocess.run(command, cwd=ROOT, check=True)


def latest_report(symbol: str, out_dir: Path, explicit_date: str = "") -> ReportPaths:
    safe_symbol = symbol.upper()
    if explicit_date:
        stem = f"{safe_symbol}_{explicit_date}_wave"
        paths = ReportPaths(
            explicit_date,
            out_dir / "charts" / f"{stem}.png",
            out_dir / "posts" / f"{stem}.md",
            out_dir / "data" / f"{stem}.json",
        )
        ensure_paths(paths)
        return paths

    posts = sorted((out_dir / "posts").glob(f"{safe_symbol}_*_wave.md"))
    if not posts:
        raise FileNotFoundError(f"No report posts found under {out_dir / 'posts'}")

    latest_post = posts[-1]
    stem = latest_post.stem
    date = stem.removeprefix(f"{safe_symbol}_").removesuffix("_wave")
    paths = ReportPaths(
        date,
        out_dir / "charts" / f"{stem}.png",
        latest_post,
        out_dir / "data" / f"{stem}.json",
    )
    ensure_paths(paths)
    return paths


def ensure_paths(paths: ReportPaths) -> None:
    missing = [str(path) for path in (paths.chart, paths.post, paths.data) if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing report files: " + ", ".join(missing))


def load_report_summary(paths: ReportPaths) -> tuple[str, dict]:
    post = paths.post.read_text(encoding="utf-8").strip()
    data = json.loads(paths.data.read_text(encoding="utf-8"))
    return post, data


def build_markdown(post: str, data: dict, public_base_url: str = "") -> str:
    symbol = data.get("symbol", "BTC-USD")
    as_of = data.get("as_of", datetime.now().strftime("%Y-%m-%d"))
    current_price = data.get("current_price")
    price_line = f"> 当前价：{current_price:,.2f}" if isinstance(current_price, (int, float)) else ""

    lines = [
        f"**{symbol} 短期波浪分析 {as_of}**",
        price_line,
        "",
        post.replace("$", ""),
    ]
    if public_base_url:
        date = as_of
        chart_url = f"{public_base_url.rstrip('/')}/reports/charts/{symbol}_{date}_wave.png"
        lines.extend(["", f"[查看波浪图]({chart_url})"])
    return "\n".join(line for line in lines if line is not None)


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


def send_image(webhook: str, image_path: Path, dry_run: bool) -> None:
    image_bytes = image_path.read_bytes()
    payload = {
        "msgtype": "image",
        "image": {
            "base64": base64.b64encode(image_bytes).decode("ascii"),
            "md5": hashlib.md5(image_bytes).hexdigest(),
        },
    }
    post_json(webhook, payload, dry_run)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out).resolve()

    if not args.skip_generate:
        run_wave_script(args)

    paths = latest_report(args.symbol, out_dir, args.date)
    post, data = load_report_summary(paths)
    webhook = os.environ.get("WECHAT_WEBHOOK", "").strip()
    public_base_url = os.environ.get("PUBLIC_BASE_URL", "").strip()
    dry_run = args.dry_run or not webhook

    markdown = build_markdown(post, data, public_base_url)
    send_markdown(webhook, markdown, dry_run)
    if args.send_image:
        send_image(webhook, paths.chart, dry_run)

    mode = "dry-run" if dry_run else "sent"
    print(f"{mode}: {paths.post.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
