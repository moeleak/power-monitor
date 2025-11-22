#!/usr/bin/env python3
"""Fetch the remaining electricity data and emit a markdown or JSON report."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from textwrap import shorten
from typing import Any, Optional

import requests
import yaml
from bs4 import BeautifulSoup

DEFAULT_BASE_URL = "https://www.wap.ekm365.com/nat/pay.aspx"
DEFAULT_MID = "20710001759"
DEFAULT_URL = f"{DEFAULT_BASE_URL}?mid={DEFAULT_MID}"
SNIPPET_LIMIT = 2000
PLACEHOLDER_PATTERN = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


class PowerMonitorError(RuntimeError):
    """Raised when we fail to fetch or parse the power data."""


@dataclass
class PowerInfo:
    meter_name: Optional[str] = None
    meter_id: Optional[str] = None
    remaining_kwh: Optional[float] = None
    remaining_amount_cny: Optional[float] = None
    price_per_kwh: Optional[float] = None


@dataclass
class PowerReport:
    url: str
    fetched_at: datetime
    info: PowerInfo
    snippet: str
    success: bool
    error: Optional[str] = None


def load_config(path: Optional[str]) -> dict[str, Any]:
    candidate = path or os.getenv("POWER_MONITOR_CONFIG") or "config.yaml"
    config_path = Path(candidate)
    if not config_path.is_file():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise PowerMonitorError("config.yaml wrong")
    return data


def lookup(config: dict[str, Any], *keys: str) -> Optional[Any]:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def url_from_mid(mid: str, base_url: Optional[str]) -> str:
    base = (base_url or DEFAULT_BASE_URL).rstrip("?")
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}mid={mid}"


def env_string(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def resolve_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    match = PLACEHOLDER_PATTERN.match(stripped)
    if match:
        env_value = env_string(match.group(1))
        return env_value
    return stripped


def config_string(config: dict[str, Any], *keys: str) -> Optional[str]:
    return resolve_string(lookup(config, *keys))


def first_non_none(*values: Optional[str]) -> Optional[str]:
    for value in values:
        if value:
            return value
    return None


def resolve_url(cli_url: Optional[str], config: dict[str, Any]) -> str:
    if cli_url:
        return cli_url

    env_url = env_string("POWER_MONITOR_URL")
    if env_url:
        return env_url

    config_url = first_non_none(
        config_string(config, "url"),
        config_string(config, "meter", "url"),
    )
    if config_url:
        return config_url

    mid = env_string("POWER_MONITOR_MID") or first_non_none(
        config_string(config, "mid"),
        config_string(config, "meter", "mid"),
    )
    base = env_string("POWER_MONITOR_BASE_URL") or first_non_none(
        config_string(config, "base_url"),
        config_string(config, "meter", "base_url"),
    )
    if mid:
        return url_from_mid(mid, base)

    return DEFAULT_URL


def fetch_page(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def normalize_label(text: str) -> str:
    return "".join(text.replace("：", ":").split()).replace(":", "")


def parse_numeric(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def find_value(soup: BeautifulSoup, keyword: str) -> Optional[str]:
    target = normalize_label(keyword)
    for span in soup.find_all("span"):
        span_text = span.get_text(strip=True)
        if not span_text:
            continue
        if normalize_label(span_text).startswith(target):
            label = span.find_next("label")
            if label:
                return label.get_text(strip=True)
    return None


def extract_power_info(html: str) -> tuple[PowerInfo, str]:
    soup = BeautifulSoup(html, "html.parser")
    meter_name = find_value(soup, "表名称")
    meter_id = find_value(soup, "表号")
    remaining_kwh = parse_numeric(find_value(soup, "剩余电量"))
    remaining_amount = parse_numeric(find_value(soup, "剩余金额"))
    price_per_kwh = parse_numeric(find_value(soup, "综合费用"))
    snippet = shorten(
        " ".join(s.strip() for s in soup.stripped_strings),
        width=SNIPPET_LIMIT,
        placeholder="...",
    )
    info = PowerInfo(
        meter_name=meter_name,
        meter_id=meter_id,
        remaining_kwh=remaining_kwh,
        remaining_amount_cny=remaining_amount,
        price_per_kwh=price_per_kwh,
    )
    return info, snippet


def collect_report(url: str) -> PowerReport:
    html = fetch_page(url)
    info, snippet = extract_power_info(html)
    success = info.remaining_kwh is not None
    error = None if success else "页面中缺少“剩余电量”字段"
    return PowerReport(
        url=url,
        fetched_at=datetime.now(timezone(timedelta(hours=8))),
        info=info,
        snippet=snippet,
        success=success,
        error=error,
    )


def format_value(value: Optional[float]) -> str:
    if value is None:
        return "未知"
    return f"{value:.2f}"


def render_markdown(report: PowerReport) -> str:
    fetched = report.fetched_at.strftime("%Y-%m-%d %H:%M:%S %Z")
    info = report.info
    lines = [
        "# 宿舍电费情况",
        f"- 时间: {fetched}",
        f"- 剩余电量(kWh): {format_value(info.remaining_kwh)}",
        f"- 剩余金额(元): {format_value(info.remaining_amount_cny)}",
    ]
    if report.error:
        lines.append(f"- 错误: {report.error}")
    lines.append("")
    return "\n".join(lines)


def render_json(report: PowerReport) -> str:
    payload = {
        "url": report.url,
        "fetched_at": report.fetched_at.isoformat(),
        "success": report.success,
        "error": report.error,
        "info": asdict(report.info),
        "snippet": report.snippet,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def write_output(text: str, destination: Optional[str]) -> None:
    if not destination:
        print(text)
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        help="Override the meter URL instead of using POWER_MONITOR_URL/config",
    )
    parser.add_argument(
        "--config",
        help="Path to config.yaml (default: config.yaml or POWER_MONITOR_CONFIG)",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output",
        help="Write the generated report to this file instead of stdout",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    url = resolve_url(args.url, config)

    try:
        report = collect_report(url)
    except Exception as exc:
        report = PowerReport(
            url=url,
            fetched_at=datetime.now(timezone.utc),
            info=PowerInfo(),
            snippet="",
            success=False,
            error=str(exc),
        )

    if args.format == "json":
        output = render_json(report)
    else:
        output = render_markdown(report)

    write_output(output, args.output)

    if not report.success:
        raise PowerMonitorError(report.error or "Power monitor failed")


if __name__ == "__main__":
    try:
        main()
    except PowerMonitorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
