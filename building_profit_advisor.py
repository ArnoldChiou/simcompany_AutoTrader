"""Read owned SimCompanies buildings and rank their products by estimated Q0 gross margin.

This is read-only: it opens the authenticated Landscape/building pages and never
starts production, purchases goods, or changes company data.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import argparse
import os
from pathlib import Path, PurePosixPath
import re
import sys
import time
from typing import Any
from urllib.parse import urlsplit

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from driver_utils import initialize_driver

GAME = "https://www.simcompanies.com"
SIMCOTOOLS_RESOURCE = "https://api.simcotools.com/v1/realms/{realm}/market/resources/{resource_id}"
LANDSCAPE = f"{GAME}/landscape/"
PROFILE_ENV = "USER_DATA_DIR_construction_monitor"
REQUEST_DELAY_SECONDS = 0.15


@dataclass(frozen=True)
class Building:
    path: str
    name: str
    code: str | None


@dataclass(frozen=True)
class Product:
    resource_id: int
    name: str
    input_quantities: dict[int, Decimal]
    market_tradable: bool = True


@dataclass(frozen=True)
class MarketQuote:
    name: str
    quality_zero_price: Decimal | None
    timestamp: str | None
    price_source: str = "daily VWAP"


def deduplicate_buildings(buildings: list[Building]) -> list[Building]:
    """Keep one landscape entry per building URL, preserving page order."""
    unique: dict[str, Building] = {}
    for building in buildings:
        unique.setdefault(building.path, building)
    return list(unique.values())


def products_for_building(building_code: str, resource_constants: dict[str, dict[str, Any]]) -> set[int]:
    """Return every product resource produced by a building DB code."""
    result = set()
    for raw_id, definition in resource_constants.items():
        if not isinstance(definition, dict):
            continue
        if str(definition.get("producedAt", "")) != str(building_code):
            continue
        try:
            result.add(int(raw_id))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"商品常數 ID 無效：{raw_id!r}") from exc
    return result


def calculate_unit_gross_profit(
    product: Product,
    output_price: Decimal,
    input_prices: dict[int, Decimal],
) -> Decimal | None:
    """Subtract recipe input reference costs from output price; None if any required quote is missing."""
    if not output_price.is_finite() or output_price <= 0:
        return None
    total = output_price
    for resource_id, quantity in product.input_quantities.items():
        price = input_prices.get(resource_id)
        if price is None or not price.is_finite() or price <= 0:
            return None
        total -= quantity * price
    return total


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _resource_code_by_name(resource_constants: dict[str, dict[str, Any]]) -> dict[str, tuple[int, str]]:
    """Match a production-card label to an exact resource-image slug."""
    by_slug: dict[str, tuple[int, str]] = {}
    for raw_id, definition in resource_constants.items():
        if not isinstance(definition, dict) or not definition.get("image"):
            continue
        slug = PurePosixPath(urlsplit(str(definition["image"])).path).stem
        try:
            resource_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"商品常數 ID 無效：{raw_id!r}") from exc
        key = _normalise(slug)
        if key in by_slug and by_slug[key][0] != resource_id:
            raise ValueError(f"多個商品共用圖示名稱 {slug!r}，無法安全識別。")
        by_slug[key] = (resource_id, str(definition.get("producedAt", "")))
    return by_slug


def _get_json(driver, path: str) -> Any:
    script = r"""
const path = arguments[0], done = arguments[arguments.length - 1];
fetch(path, {credentials: 'same-origin', headers: {Accept: 'application/json'}})
  .then(async response => {
    const text = await response.text();
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 160)}`);
    try { return JSON.parse(text); } catch (_) { throw new Error('API 回傳非 JSON'); }
  })
  .then(value => done({ok: true, value}))
  .catch(error => done({ok: false, error: String(error)}));
"""
    result = driver.execute_async_script(script, path)
    if not result.get("ok"):
        raise RuntimeError(f"SimCompanies API 讀取失敗：{result.get('error', 'unknown error')}")
    return result["value"]


def _landscape_buildings(driver) -> list[Building]:
    driver.get(LANDSCAPE)
    WebDriverWait(driver, 30).until(
        lambda page: page.find_elements(By.CSS_SELECTOR, 'a[href*="/b/"]')
    )
    records = driver.execute_script(r"""
return [...new Set([...document.querySelectorAll('a[href*="/b/"]')]
  .map(a => a.getAttribute('href')))].map(path => {
    const a = document.querySelector(`a[href="${path}"]`);
    const status = a?.querySelector('[aria-label]')?.getAttribute('aria-label') || '';
    return {path, status};
  });
""")
    found: list[Building] = []
    for record in records:
        match = re.search(r"/b/(\d+)/", record.get("path", ""))
        if not match:
            continue
        status = str(record.get("status", ""))
        name = status.split(":", 1)[0].strip() if ":" in status else ""
        found.append(Building(f"/b/{match.group(1)}/", name or "未命名建築", None))
    return deduplicate_buildings(found)


def _production_building_codes(
    driver,
    buildings: list[Building],
    resource_constants: dict[str, dict[str, Any]],
) -> tuple[list[Building], list[str]]:
    slug_map = _resource_code_by_name(resource_constants)
    resolved: list[Building] = []
    issues: list[str] = []
    for building in buildings:
        driver.get(GAME + building.path)
        try:
            WebDriverWait(driver, 20).until(
                lambda page: page.find_elements(By.CSS_SELECTOR, "h3")
                and "fetching building info" not in page.execute_script(
                    "return (document.body.innerText || '').toLowerCase()"
                )
            )
        except Exception as exc:
            issues.append(f"{building.name} {building.path}：建築頁未載入（{type(exc).__name__}）")
            resolved.append(building)
            continue
        page_data = driver.execute_script(r"""
const headings = [...document.querySelectorAll('h3')].map(h => (h.innerText || '').trim()).filter(Boolean);
const production = headings.find(text => text.split('\n')[0].trim().toLowerCase() === 'production');
const title = headings[0] || '';
return {title, production};
""") or {}
        page_title = str(page_data.get("title") or building.name).strip()
        production_heading = str(page_data.get("production") or "")
        output_label = production_heading.splitlines()[-1].strip() if production_heading else ""
        code = None
        if output_label:
            matched = slug_map.get(_normalise(output_label))
            if matched:
                code = matched[1]
        resolved.append(Building(building.path, page_title or building.name, code))
        # A building page can be valid but have no active product card; it is reported
        # as unresolved rather than assigning a product family based on a guess.
        if code is None:
            issues.append(f"{page_title or building.name} {building.path}：無法從頁面產品標籤確認生產類型")
    return resolved, issues


def _quote_from_payload(payload: dict[str, Any]) -> MarketQuote:
    resource = payload.get("resource")
    if not isinstance(resource, dict):
        raise ValueError("SimcoTools 回傳缺少 resource 資料")
    summaries = resource.get("summariesByQuality")
    if not isinstance(summaries, list):
        raise ValueError(f"{resource.get('resourceName', '商品')} 缺少市場摘要")
    summary = next((item for item in summaries if str(item.get("quality")) == "0"), None)
    price, timestamp, price_source = None, None, "unavailable"
    if summary:
        candle = summary.get("lastDayCandlestick") or {}
        try:
            parsed_vwap = Decimal(str(candle["vwap"]))
            if parsed_vwap.is_finite() and parsed_vwap > 0:
                price = parsed_vwap
                timestamp = str(candle.get("date") or "") or None
                price_source = "daily VWAP"
        except (KeyError, TypeError, InvalidOperation):
            pass
        if price is None:
            try:
                parsed_trade = Decimal(str(summary["price"]))
                if parsed_trade.is_finite() and parsed_trade > 0:
                    price = parsed_trade
                    timestamp = str(summary.get("timestamp") or "") or None
                    price_source = "latest trade"
            except (KeyError, TypeError, InvalidOperation):
                pass
    return MarketQuote(
        str(resource.get("resourceName") or f"ID {resource.get('resourceId', '?')}"),
        price,
        timestamp,
        price_source,
    )


def fetch_quotes(resource_ids: set[int], realm_id: int, session: requests.Session | None = None) -> dict[int, MarketQuote]:
    client = session or requests.Session()
    quotes: dict[int, MarketQuote] = {}
    for index, resource_id in enumerate(sorted(resource_ids)):
        url = SIMCOTOOLS_RESOURCE.format(realm=realm_id, resource_id=resource_id)
        response = client.get(url, timeout=25)
        response.raise_for_status()
        quotes[resource_id] = _quote_from_payload(response.json())
        if index + 1 < len(resource_ids):
            time.sleep(REQUEST_DELAY_SECONDS)
    return quotes


def build_product_rows(
    building_code: str,
    resource_constants: dict[str, dict[str, Any]],
    quotes: dict[int, MarketQuote],
) -> list[tuple[Product, MarketQuote, Decimal | None]]:
    rows = []
    for resource_id in sorted(products_for_building(building_code, resource_constants)):
        definition = resource_constants[str(resource_id)]
        try:
            inputs = {
                int(input_id): Decimal(str(quantity))
                for input_id, quantity in (definition.get("producedFrom") or {}).items()
            }
            if any(not quantity.is_finite() or quantity < 0 for quantity in inputs.values()):
                raise ValueError("產品配方數量無效")
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError(f"商品 ID {resource_id} 的配方資料異常") from exc
        tradable = bool(definition.get("isExchangeTradable", False))
        product_quote = quotes.get(resource_id) if tradable else None
        image = str(definition.get("image", ""))
        fallback_name = PurePosixPath(urlsplit(image).path).stem.replace("-", " ").title()
        product_name = product_quote.name if product_quote else fallback_name or f"商品 ID {resource_id}"
        product = Product(
            resource_id,
            product_name,
            inputs,
            tradable,
        )
        input_prices = {item_id: quote.quality_zero_price for item_id, quote in quotes.items()}
        product_quote = product_quote or MarketQuote(product_name, None, None)
        profit = calculate_unit_gross_profit(product, product_quote.quality_zero_price, input_prices) if product_quote.quality_zero_price else None
        rows.append((product, product_quote, profit))
    return rows


def recommend_best_product(
    driver,
    building_url: str,
    completed_product_name: str | None = None,
) -> tuple[str, Decimal, Decimal] | None:
    """Return (product name, Q0 reference price, unit gross margin) for one building.

    Uses the caller's authenticated Selenium driver so the completion monitor
    does not launch a competing Chrome process or a second profile session.
    This function is strictly read-only and never submits production orders.
    """
    parsed_url = urlsplit(building_url)
    if parsed_url.scheme != "https" or parsed_url.netloc != "www.simcompanies.com":
        raise ValueError("建築網址不是 SimCompanies 官方網址。")
    match = re.fullmatch(r"/b/(\d+)/?", parsed_url.path)
    if not match:
        raise ValueError("建築網址路徑格式不正確。")
    path = f"/b/{match.group(1)}/"
    driver.get(building_url)
    auth = _get_json(driver, "/api/v3/companies/auth-data/")
    realm_id = ((auth or {}).get("authCompany") or {}).get("realmId")
    if realm_id is None:
        return None
    resource_constants = _get_json(driver, "/api/v2/constants/resources/")
    if not isinstance(resource_constants, dict):
        return None
    resolved, _issues = _production_building_codes(
        driver, [Building(path, "", None)], resource_constants
    )
    code = resolved[0].code if resolved else None
    if not code and completed_product_name:
        product_label = re.sub(r"\s+Q\d+\s*$", "", completed_product_name.strip(), flags=re.IGNORECASE)
        product_match = _resource_code_by_name(resource_constants).get(_normalise(product_label))
        if product_match:
            code = product_match[1]
    if not code:
        return None
    produced_ids = products_for_building(code, resource_constants)
    tradable_ids = {
        resource_id for resource_id in produced_ids
        if resource_constants[str(resource_id)].get("isExchangeTradable", False)
    }
    input_ids = set()
    for resource_id in tradable_ids:
        input_ids.update(
            int(input_id)
            for input_id in (resource_constants[str(resource_id)].get("producedFrom") or {})
        )
    if not tradable_ids:
        return None
    quotes = fetch_quotes(tradable_ids | input_ids, int(realm_id))
    rows = build_product_rows(code, resource_constants, quotes)
    ranked = [
        (product, quote, profit)
        for product, quote, profit in rows
        if product.market_tradable and quote.quality_zero_price is not None and profit is not None
    ]
    if not ranked:
        return None
    product, quote, gross_margin = max(ranked, key=lambda row: row[2])
    return product.name, quote.quality_zero_price, gross_margin


def _money(value: Decimal | None) -> str:
    return "無報價" if value is None else f"${value:,.3f}".rstrip("0").rstrip(".")


def render_report(
    buildings: list[Building],
    rows_by_code: dict[str, list[tuple[Product, MarketQuote, Decimal | None]]],
    unresolved: list[str],
    checked_at: str,
) -> str:
    lines = [
        "SimCompanies 建築產品利潤比較（唯讀）",
        f"資料時間：{checked_at}",
        f"Landscape 建築數：{len(buildings)}（重複建築已去除）",
        "計算方式：優先用 Q0 日 VWAP，缺少時回退最新成交價；減去配方投入成本。未扣工資、運輸、交易費與建築升級差異。",
        "",
    ]
    groups: dict[tuple[str, str | None], list[Building]] = {}
    for building in buildings:
        groups.setdefault((building.name, building.code), []).append(building)
    for (name, code), instances in groups.items():
        lines.append(f"【{name}{f'（生產類型 {code}）' if code else ''}】建築數：{len(instances)}")
        if not code:
            lines.append("  產品：無法確認（本次未取得有效生產產品資料）")
            lines.append("")
            continue
        product_rows = rows_by_code.get(code, [])
        if not product_rows:
            lines.append("  產品：無可比較報價")
            lines.append("")
            continue
        ranked = sorted(
            (row for row in product_rows if row[0].market_tradable and row[2] is not None),
            key=lambda row: (row[2], row[0].name),
            reverse=True,
        )
        for product, quote, profit in product_rows:
            if not product.market_tradable:
                result = "不可交易，無交易所價格"
            elif quote.quality_zero_price is None:
                result = "缺少 Q0 日 VWAP 與最新成交價，毛利無法計算"
            else:
                result = f"單位毛利 {_money(profit)}" if profit is not None else "單位毛利無法計算（缺少投入品報價）"
            market_price = quote.quality_zero_price if product.market_tradable else None
            price_label = {
                "daily VWAP": "Q0 日 VWAP",
                "latest trade": "Q0 最新成交價",
            }.get(quote.price_source, "Q0 報價")
            lines.append(f"  • {product.name} — {price_label} {_money(market_price)}；{result}")
        if ranked:
            best = ranked[0]
            lines.append(f"  ★ 毛利最高：{best[0].name}（{_money(best[2])}/單位）")
        else:
            lines.append("  ★ 無足夠報價可判定毛利最高產品")
        lines.append("")
    if unresolved:
        lines.append("未能確認的建築／資料（已避免猜測）：")
        lines.extend(f"  • {issue}" for issue in unresolved)
    return "\n".join(lines).rstrip() + "\n"


def run(profile: str | None = None) -> str:
    profile = profile or os.getenv("SIMCOMPANIES_VWAP_PROFILE") or os.getenv(PROFILE_ENV)
    if not profile or not Path(profile).is_dir():
        raise RuntimeError(f"請在 .env 設定已登入的 {PROFILE_ENV} Chrome profile。")
    driver = initialize_driver(user_data_dir=profile)
    try:
        driver.get(GAME + "/landscape/")
        auth = _get_json(driver, "/api/v3/companies/auth-data/")
        company = (auth or {}).get("authCompany") or {}
        realm_id = company.get("realmId")
        if realm_id is None:
            raise RuntimeError("無法讀取目前公司的遊戲伺服器（realm）。")
        buildings = _landscape_buildings(driver)
        if not buildings:
            raise RuntimeError("Landscape 沒有回傳任何建築；已停止以免產生不完整報告。")
        resource_constants = _get_json(driver, "/api/v2/constants/resources/")
        if not isinstance(resource_constants, dict):
            raise RuntimeError("SimCompanies 商品常數格式異常。")
        buildings, unresolved = _production_building_codes(driver, buildings, resource_constants)
        codes = {building.code for building in buildings if building.code}
        produced_ids = set().union(*(products_for_building(code, resource_constants) for code in codes)) if codes else set()
        tradable_ids = {
            resource_id for resource_id in produced_ids
            if resource_constants[str(resource_id)].get("isExchangeTradable", False)
        }
        input_ids = set()
        for resource_id in tradable_ids:
            definition = resource_constants.get(str(resource_id), {})
            input_ids.update(int(key) for key in (definition.get("producedFrom") or {}))
        all_ids = tradable_ids | input_ids
        if not all_ids:
            raise RuntimeError("沒有找到可比較的可交易產品，已停止產生空報告。")
        quotes = fetch_quotes(all_ids, int(realm_id))
        rows_by_code = {
            code: build_product_rows(code, resource_constants, quotes) for code in codes
        }
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime())
        return render_report(buildings, rows_by_code, unresolved, timestamp)
    finally:
        driver.quit()


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(description="列出建築產品並以 Q0 日 VWAP（缺少時回退最新成交價）比較單位毛利")
    parser.add_argument("--profile", help="已登入 SimCompanies 的 Chrome user-data-dir")
    args = parser.parse_args(argv)
    try:
        report = run(args.profile)
    except Exception as exc:
        print(f"執行失敗：{exc}", file=sys.stderr)
        return 1
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
