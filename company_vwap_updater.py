"""Refresh warehouse listings in the SimCompanies public company description.

Reads the authenticated warehouse, obtains daily VWAP from SimcoTools, then
uses SimCompanies' own company-settings form to update the listing.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import os
from pathlib import Path, PurePosixPath
import time
from typing import Any
from urllib.parse import urlsplit

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from driver_utils import initialize_driver

GAME = "https://www.simcompanies.com"
MARKET_API = "https://api.simcotools.com/v1/realms/{realm}/market/resources/{resource_id}"
PROFILE_ENV = "USER_DATA_DIR_construction_monitor"
MAX_DESCRIPTION_LENGTH = 2000
VWAP_DISCOUNT_FACTOR = Decimal("0.98")
RESOURCE_CONSTANTS_API = f"{GAME}/api/v2/constants/resources/"
BACKUP_DIRECTORY = Path("record/company_description_backups")


def resolve_profile(profile_dir: str | None = None) -> str:
    """Use the explicit profile or the existing construction-monitor profile."""
    profile = profile_dir or os.getenv("SIMCOMPANIES_VWAP_PROFILE") or os.getenv(PROFILE_ENV)
    if not profile:
        raise RuntimeError(
            f"請先在 .env 設定 {PROFILE_ENV}（或 SIMCOMPANIES_VWAP_PROFILE），"
            "指定已登入 SimCompanies 的 Chrome profile。"
        )
    if not Path(profile).is_dir():
        raise FileNotFoundError(f"Chrome profile 不存在：{profile}")
    return profile


def aggregate_inventory(records: list[dict[str, Any]]) -> dict[tuple[int, int], Decimal]:
    """Sum positive, unblocked warehouse stock by resource ID and quality."""
    totals: dict[tuple[int, int], Decimal] = {}
    for record in records:
        if record.get("blocked", False):
            continue
        try:
            amount = Decimal(str(record.get("amount", 0)))
            resource_id = int(record["kind"])
            quality = int(record["quality"])
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError(f"倉庫資料格式不正確：{record!r}") from exc
        if amount <= 0:
            continue
        key = (resource_id, quality)
        totals[key] = totals.get(key, Decimal("0")) + amount
    return totals


def _get_json(driver, path: str) -> Any:
    """Read a same-origin authenticated JSON API without handling secrets."""
    script = r"""
const path = arguments[0], done = arguments[arguments.length - 1];
fetch(path, {credentials: 'same-origin', headers: {Accept: 'application/json'}})
  .then(async response => {
    const text = await response.text();
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 250)}`);
    try { return JSON.parse(text); } catch (_) { return text; }
  })
  .then(value => done({ok: true, value}))
  .catch(error => done({ok: false, error: String(error)}));
"""
    result = driver.execute_async_script(script, path)
    if not result.get("ok"):
        raise RuntimeError(f"SimCompanies API 讀取失敗：{result.get('error', 'unknown error')}")
    return result.get("value")


def get_account_data(driver) -> tuple[int, int, list[dict[str, Any]], str]:
    auth = _get_json(driver, "/api/v3/companies/auth-data/")
    company = (auth or {}).get("authCompany") or {}
    company_id, realm_id = company.get("companyId"), company.get("realmId")
    if not company_id or realm_id is None:
        raise RuntimeError("此 Chrome profile 沒有登入 SimCompanies，或無法識別目前公司。")
    inventory = _get_json(driver, f"/api/v3/resources/{company_id}/")
    description = _get_json(driver, f"/api/v2/companies/{company_id}/free-text/")
    if not isinstance(inventory, list) or not isinstance(description, str):
        raise RuntimeError("SimCompanies 回傳的倉庫或公司簡介格式與預期不同。")
    return int(company_id), int(realm_id), inventory, description


def fetch_market_data(resource_ids: set[int], realm_id: int, session=None) -> dict[int, dict[str, Any]]:
    client = session or requests.Session()
    result = {}
    for index, resource_id in enumerate(sorted(resource_ids)):
        url = MARKET_API.format(realm=realm_id, resource_id=resource_id)
        response = client.get(url, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload.get("resource"), dict):
            raise ValueError(f"SimcoTools 回傳格式異常，商品 ID={resource_id}")
        result[resource_id] = payload
        if index + 1 < len(resource_ids):
            time.sleep(0.15)
    return result


def fetch_resource_constants(session=None) -> dict[str, dict[str, Any]]:
    """Fetch the game's resource-image metadata for matching warehouse cards."""
    client = session or requests.Session()
    response = client.get(RESOURCE_CONSTANTS_API, timeout=20)
    response.raise_for_status()
    constants = response.json()
    if not isinstance(constants, dict):
        raise ValueError("SimCompanies resource constants 回傳格式異常。")
    return constants


def map_warehouse_categories(
    category_groups: list[dict[str, Any]],
    resource_constants: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[int, str]]:
    """Map warehouse list headings to item IDs through the rendered resource icons."""
    image_to_id: dict[str, int] = {}
    for raw_id, definition in resource_constants.items():
        if not isinstance(definition, dict) or not isinstance(definition.get("image"), str):
            continue
        slug = PurePosixPath(urlsplit(definition["image"]).path).stem
        try:
            resource_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"SimCompanies resource constant ID 無效：{raw_id!r}") from exc
        existing_id = image_to_id.get(slug)
        if existing_id is not None and existing_id != resource_id:
            raise ValueError(f"SimCompanies 圖示 {slug!r} 對應多個商品 ID，無法安全分類。")
        image_to_id[slug] = resource_id

    category_order: list[str] = []
    category_by_resource: dict[int, str] = {}
    for group in category_groups:
        category = str(group.get("category", "")).strip()
        images = group.get("images")
        if not category or not isinstance(images, list):
            raise ValueError("倉庫分類 DOM 格式異常。")
        if category not in category_order:
            category_order.append(category)
        for image_url in images:
            if not isinstance(image_url, str) or not image_url:
                raise ValueError(f"倉庫分類 {category} 缺少商品圖示 URL。")
            filename = PurePosixPath(urlsplit(image_url).path).name
            hashed_stem = PurePosixPath(filename).stem
            matches = [
                (slug, resource_id)
                for slug, resource_id in image_to_id.items()
                if hashed_stem == slug or hashed_stem.startswith(slug + ".")
            ]
            if not matches:
                raise ValueError(f"無法將倉庫分類 {category} 的圖示映射到商品 ID：{filename}")
            longest = max(len(slug) for slug, _ in matches)
            best = {(slug, resource_id) for slug, resource_id in matches if len(slug) == longest}
            if len(best) != 1:
                raise ValueError(f"倉庫圖示 {filename!r} 對應多個商品 ID，已停止分類。")
            _, resource_id = next(iter(best))
            previous = category_by_resource.get(resource_id)
            if previous is not None and previous != category:
                raise ValueError(
                    f"商品 ID {resource_id} 同時出現在倉庫分類 {previous} 與 {category}。"
                )
            category_by_resource[resource_id] = category
    if not category_order:
        raise ValueError("無法從倉庫頁讀取商品分類。")
    return category_order, category_by_resource


def get_warehouse_categories(
    driver, resource_constants: dict[str, dict[str, Any]]
) -> tuple[list[str], dict[int, str]]:
    """Read category labels and resource cards from the actual warehouse UI."""
    groups = WebDriverWait(driver, 60).until(
        lambda page: [
            group
            for group in page.find_elements(By.CSS_SELECTOR, '#root [role="list"][aria-label]')
            if group.find_elements(By.CSS_SELECTOR, '[role="link"][aria-label]')
        ]
    )
    category_groups = []
    for group in groups:
        images = []
        for card in group.find_elements(By.CSS_SELECTOR, '[role="link"][aria-label]'):
            image = card.find_elements(By.TAG_NAME, "img")
            if not image:
                raise ValueError(f"倉庫分類 {group.get_attribute('aria-label')} 有商品卡片缺少圖示。")
            images.append(image[0].get_attribute("src"))
        category_groups.append(
            {"category": group.get_attribute("aria-label"), "images": images}
        )
    return map_warehouse_categories(category_groups, resource_constants)


def _vwap(payload: dict[str, Any], quality: int) -> Decimal:
    resource = payload.get("resource") or {}
    summaries = resource.get("summariesByQuality") or []
    summary = next((entry for entry in summaries if int(entry.get("quality", -1)) == quality), None)
    candle = (summary or {}).get("lastDayCandlestick") or {}
    try:
        value = Decimal(str(candle["vwap"]))
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise ValueError(
            f"{resource.get('resourceName', '商品')}（ID {resource.get('resourceId', '?')}）Q{quality} 沒有 VWAP 資料"
        ) from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"商品 ID {resource.get('resourceId', '?')} Q{quality} 的 VWAP 無效")
    return value


def format_listing_rows(
    inventory: dict[tuple[int, int], Any],
    market_by_id: dict[int, dict[str, Any]],
    category_by_resource: dict[int, str],
    category_order: list[str],
    *,
    use_product_names: bool = False,
) -> list[str]:
    """Group discounted VWAP prices in the same order as warehouse sections."""
    if not category_order:
        raise ValueError("倉庫頁沒有可用的分類順序。")
    grouped: dict[str, list[tuple[int, int, str]]] = {}
    for resource_id, quality in inventory:
        payload = market_by_id.get(resource_id)
        if payload is None:
            raise ValueError(f"缺少商品 ID {resource_id} Q{quality} 的 SimcoTools 資料")
        category = category_by_resource.get(resource_id)
        if category is None or category not in category_order:
            raise ValueError(f"倉庫頁找不到商品 ID {resource_id} 的分類，已停止更新。")
        discounted = _vwap(payload, quality) * VWAP_DISCOUNT_FACTOR
        decimal_places = 3 if discounted < Decimal("1") else 2
        quantum = Decimal("0.001") if decimal_places == 3 else Decimal("0.01")
        price = discounted.quantize(quantum, rounding=ROUND_HALF_UP)
        product = str(payload["resource"].get("resourceName") or f"Product {resource_id}") if use_product_names else f":re-{resource_id}:"
        product = " ".join(product.split())
        row = f"Q{quality} | {product} | ${price:.{decimal_places}f}"
        grouped.setdefault(category, []).append((resource_id, quality, row))

    rows = ["Q | Product | Price"]
    for category in category_order:
        entries = grouped.get(category)
        if not entries:
            continue
        rows.append(f"[{category}]")
        rows.extend(row for _, _, row in sorted(entries))
    return rows


def replace_listing(description: str, rows: list[str]) -> str:
    """Replace only current inventory rows; preserve header, separator and footer."""
    newline = "\r\n" if "\r\n" in description else "\n"
    trailing_newlines = len(description) - len(description.rstrip("\r\n"))
    lines = description.rstrip("\r\n").splitlines()
    header = next((i for i, line in enumerate(lines) if "Selling @VWAP" in line), None)
    if header is None:
        raise ValueError("公司簡介找不到 Selling @VWAP 標題，為避免覆蓋其他內容已停止。")
    divider = next(
        (i for i in range(header + 1, len(lines))
         if len(lines[i].strip()) >= 10 and set(lines[i].strip()) == {"-"}),
        None,
    )
    if divider is None:
        raise ValueError("公司簡介找不到分隔線，為避免覆蓋其他內容已停止。")
    updated = newline.join(lines[:header + 1] + rows + lines[divider:]) + newline * trailing_newlines
    if len(updated) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(f"新公司簡介為 {len(updated)} 字，超過遊戲的 {MAX_DESCRIPTION_LENGTH} 字上限。")
    return updated


def company_settings_url(realm_id: int) -> str:
    return f"{GAME}/account-settings/settings/{realm_id}/"


def save_description_via_ui(driver, realm_id: int, company_id: int, updated: str) -> None:
    """Submit via the official settings textarea, then verify by reading back."""
    driver.get(company_settings_url(realm_id))
    wait = WebDriverWait(driver, 20)
    textarea = wait.until(EC.presence_of_element_located((By.TAG_NAME, "textarea")))
    textarea.clear()
    textarea.send_keys(updated)
    button = wait.until(
        lambda page: next(
            (
                candidate
                for candidate in page.find_elements(By.TAG_NAME, "button")
                if candidate.text.strip().upper() == "CHANGE"
                and candidate.is_displayed()
                and candidate.is_enabled()
            ),
            False,
        )
    )
    button.click()
    path = f"/api/v2/companies/{company_id}/free-text/"

    def saved(_driver) -> bool:
        try:
            return _get_json(_driver, path) == updated
        except RuntimeError:
            return False

    try:
        wait.until(saved)
    except Exception as exc:
        raise RuntimeError("提交後回讀公司簡介不相符，更新未能驗證。") from exc


@dataclass(frozen=True)
class UpdateResult:
    company_id: int
    realm_id: int
    item_count: int
    original_description: str
    updated_description: str
    backup_path: Path | None
    listing_text: str = ""


def update_company_description(
    profile_dir: str | None = None,
    *,
    apply: bool = True,
    logger: logging.Logger | None = None,
) -> UpdateResult:
    """Fetch all stocked qualities and, by default, update the public description."""
    profile = resolve_profile(profile_dir)
    log = logger or logging.getLogger(__name__)
    driver = initialize_driver(user_data_dir=profile)
    try:
        driver.get(f"{GAME}/headquarters/warehouse/")
        company_id, realm_id, records, current = get_account_data(driver)
        inventory = aggregate_inventory(records)
        if not inventory:
            raise RuntimeError("倉庫沒有可列出的正庫存商品，未修改公司簡介。")
        resource_constants = fetch_resource_constants()
        category_order, categories = get_warehouse_categories(driver, resource_constants)
        market = fetch_market_data({resource_id for resource_id, _ in inventory}, realm_id)
        rows = format_listing_rows(inventory, market, categories, category_order)
        updated = replace_listing(current, rows)
        listing_text = "\n".join(format_listing_rows(
            inventory, market, categories, category_order, use_product_names=True,
        ))
        backup_path = None
        if apply and updated != current:
            backup_path = BACKUP_DIRECTORY / f"company-description-{time.strftime('%Y%m%d-%H%M%S')}.txt"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_text(current, encoding="utf-8")
            save_description_via_ui(driver, realm_id, company_id, updated)
        elif apply:
            log.info("公司簡介已符合目前倉庫 VWAP，略過重複寫入。")
        return UpdateResult(company_id, realm_id, len(inventory), current, updated, backup_path, listing_text)
    finally:
        driver.quit()
