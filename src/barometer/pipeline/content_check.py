"""Read-only comparison of two rendered-content snapshots."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from barometer.domain.coverage import Coverage
from barometer.render.page import Tab

_NUMBER = re.compile(r"^[+-]?(?:\d[\d,]*)(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class Issue:
    kind: str
    path: str
    before: str
    after: str
    detail: str


def _coverage(value: Coverage | None) -> dict | None:
    if value is None or value.expected == 0:
        return None
    return {"available": value.available, "expected": value.expected,
            "percent": 100 * value.available / value.expected}


def capture_tabs(tabs: list[Tab], captured_at: dt.datetime) -> dict:
    """Capture only visible content and provenance, outside of the site repo."""
    return {
        "captured_at": captured_at.isoformat(timespec="seconds"),
        "tabs": {tab.key: {
            "title": tab.title,
            "coverage": _coverage(tab.coverage),
            "rows": {row.label: {
                "value": row.value,
                "source": row.source,
                "data_date": row.data_date,
                "fetched_at": row.fetched_at,
                "coverage": _coverage(row.coverage),
                "fundamental_coverage": _coverage(row.fundamental_coverage),
            } for row in tab.rows},
        } for tab in tabs},
    }


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    match = _NUMBER.match(value.strip())
    return float(match.group().replace(",", "")) if match else None


def _coverage_issue(path: str, before: dict | None, after: dict | None) -> Issue | None:
    if before is None or after is None:
        return None
    drop = before["percent"] - after["percent"]
    if drop <= 20:
        return None
    return Issue("coverage_drop", path, f"{before['percent']:g}%",
                 f"{after['percent']:g}%", f"下降 {drop:g} 個百分點；需人工確認")


def compare_snapshots(
    before: dict, after: dict, *, change_pct: float = 25.0,
    min_absolute: float = 5.0, score_points: float = 15.0,
) -> list[Issue]:
    """List review items without editing either snapshot or blocking publish."""
    issues: list[Issue] = []
    old_tabs, new_tabs = before["tabs"], after["tabs"]
    for tab_key in sorted(old_tabs.keys() | new_tabs.keys()):
        if tab_key not in old_tabs or tab_key not in new_tabs:
            issues.append(Issue("missing_tab", tab_key,
                                "有" if tab_key in old_tabs else "無",
                                "有" if tab_key in new_tabs else "無", "頁籤增減；需人工確認"))
            continue
        old_tab, new_tab = old_tabs[tab_key], new_tabs[tab_key]
        coverage = _coverage_issue(f"{tab_key}／涵蓋率", old_tab.get("coverage"),
                                   new_tab.get("coverage"))
        if coverage:
            issues.append(coverage)
        old_rows, new_rows = old_tab["rows"], new_tab["rows"]
        for label in sorted(old_rows.keys() | new_rows.keys()):
            path = f"{tab_key}／{label}"
            if label not in old_rows or label not in new_rows:
                issues.append(Issue("missing_row", path,
                                    "有" if label in old_rows else "無",
                                    "有" if label in new_rows else "無", "資料列增減；需人工確認"))
                continue
            old, new = old_rows[label], new_rows[label]
            for field in ("coverage", "fundamental_coverage"):
                coverage = _coverage_issue(f"{path}／{field}", old.get(field), new.get(field))
                if coverage:
                    issues.append(coverage)
            if old.get("source") != new.get("source"):
                issues.append(Issue("source_change", f"{path}／來源",
                                    old.get("source") or "—", new.get("source") or "—",
                                    "資料來源變更；需人工確認"))
            old_value, new_value = old.get("value"), new.get("value")
            if old_value == new_value:
                continue
            old_num, new_num = _number(old_value), _number(new_value)
            if old_num is None or new_num is None:
                issues.append(Issue("missing_value", f"{path}／數值",
                                    old_value or "—", new_value or "—", "數值出現或消失；需人工確認"))
                continue
            absolute = abs(new_num - old_num)
            if old.get("coverage") is not None:
                crossed = absolute > score_points
                detail = f"分數變動 {absolute:.1f} 分（門檻 {score_points:g} 分）"
            else:
                percent = abs((new_num / old_num - 1) * 100) if old_num else float("inf")
                crossed = percent > change_pct and absolute > min_absolute
                detail = f"變動 {percent:.1f}%／{absolute:.2f}（門檻 {change_pct:g}% 且 {min_absolute:g}）"
            if crossed:
                issues.append(Issue("value_jump", f"{path}／數值",
                                    old_value or "—", new_value or "—", detail + "；需人工確認"))
    return issues


def format_report(before: dict, after: dict, issues: list[Issue]) -> str:
    """Human-readable Markdown report; anomalies never become an exit gate."""
    lines = ["# 內容逐格比對", "",
             f"前次：{before['captured_at']}　｜　本次：{after['captured_at']}", "",
             f"需人工確認：{len(issues)} 項。只列異常供檢視；不修改資料、不阻擋發布。", ""]
    if issues:
        lines += ["| 位置 | 前次 | 本次 | 說明 |", "|---|---|---|---|"]
        for issue in issues:
            cells = (issue.path, issue.before, issue.after, issue.detail)
            lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |")
    else:
        lines.append("沒有超過門檻的內容變動。")
    return "\n".join(lines) + "\n"
