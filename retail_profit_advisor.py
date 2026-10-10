"""Recommend the most profitable retail product without placing an order.

The SimCompanies retail form accepts a duration (for example ``48hr``) in its
Quantity field.  This module fills that duration and the displayed average
retail price for every visible product panel, then combines the form's
per-unit retail profit with the exchange's *quantity-weighted* purchase cost.
Nothing in this module clicks Produce, Buy, or any other submit button.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import os
import re
import time
from typing import Iterable, Optional
from urllib.parse import urlparse

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement

from config import PRODUCT_CONFIGS


MARKET_URL = "https://www.simcompanies.com/api/v3/market/{realm}/{resource_id}/"
_NUMBER_PATTERN = r"(-?\$?\s*[\d,]+(?:\.\d+)?)"


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def parse_number(value: str) -> Optional[float]:
    """Parse a game-formatted money or quantity value, including negatives."""
    if value is None:
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group()) if match else None


def parse_labeled_number(text: str, labels: Iterable[str]) -> Optional[float]:
    """Return the first numeric value following one of the given UI labels."""
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}\s*:?\s*{_NUMBER_PATTERN}", text, re.IGNORECASE
        )
        if match:
            return parse_number(match.group(1))
    return None


def weighted_market_price(orders: Iterable[dict], quantity: float, quality: int = 0) -> Optional[float]:
    """Return the exchange VWAP needed to buy *quantity*, or ``None`` if short."""
    if quantity <= 0:
        return None
    valid_orders = []
    for order in orders:
        try:
            order_quality = int(order["quality"])
            price = float(order["price"])
            available = float(order["quantity"])
        except (KeyError, TypeError, ValueError):
            continue
        if order_quality >= quality and price > 0 and available > 0:
            valid_orders.append((price, available))

    remaining = quantity
    total_cost = 0.0
    for price, available in sorted(valid_orders):
        taken = min(remaining, available)
        total_cost += price * taken
        remaining -= taken
        if remaining <= 1e-9:
            return total_cost / quantity
    return None


@dataclass(frozen=True)
class RetailRecommendation:
    product: str
    quantity: float
    quality: int
    retail_profit_per_unit: float
    exchange_cost_per_unit: float
    inventory_cost_per_unit: float = 0.0
    retail_price: float = 0.0
    average_retail_price: float = 0.0

    @property
    def net_profit_per_unit(self) -> float:
        # The game's profit already deducts COGS when there is stock. Replace
        # that book cost with the current exchange cost, never deduct twice.
        return self.retail_profit_per_unit + self.inventory_cost_per_unit - self.exchange_cost_per_unit

    @property
    def net_profit_total(self) -> float:
        return self.net_profit_per_unit * self.quantity


class RetailProfitAdvisor:
    """Read the idle retail page and rank its currently visible products."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        hours: Optional[int] = None,
        target_path: Optional[str] = None,
        realm: Optional[int] = None,
        session: Optional[requests.Session] = None,
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.hours = self._positive_int(hours, "RETAIL_ADVISOR_HOURS", 48)
        self.target_path = self._normalise_path(
            target_path or os.getenv("RETAIL_ADVISOR_BUILDING_PATH", "/b/54696865/")
        )
        self.realm = self._positive_int(realm, "RETAIL_ADVISOR_REALM", 0, allow_zero=True)
        self.session = session or requests.Session()
        self.errors = []
        self.checked_at = None
        self.building_busy = False
        self.product_names = {
            _normalise(product["name"]): product["name"] for product in PRODUCT_CONFIGS
        }
        self.product_ids = {
            _normalise(product["name"]): self._resource_id(product["api_url"])
            for product in PRODUCT_CONFIGS
        }
        self.product_names_by_resource_id = {
            resource_id: self.product_names[key]
            for key, resource_id in self.product_ids.items()
            if resource_id is not None
        }

    @staticmethod
    def _positive_int(value, env_name: str, default: int, allow_zero: bool = False) -> int:
        try:
            result = int(value if value is not None else os.getenv(env_name, str(default)))
            if result > 0 or (allow_zero and result == 0):
                return result
        except (TypeError, ValueError):
            pass
        return default

    @staticmethod
    def _resource_id(api_url: str) -> Optional[int]:
        match = re.search(r"/market/\d+/(\d+)/", api_url or "")
        return int(match.group(1)) if match else None

    @staticmethod
    def _normalise_path(value: str) -> str:
        path = urlparse(value).path if "://" in value else value
        return "/" + path.strip("/") + "/"

    def is_target(self, building_url: str) -> bool:
        return self._normalise_path(building_url) == self.target_path

    def analyse(self, driver, building_url: str) -> list[RetailRecommendation]:
        """Calculate recommendations from an already authenticated WebDriver.

        The caller supplies the current driver so this can run directly after
        the existing idle notification, without opening a second browser.
        """
        if not self.is_target(building_url):
            return []
        try:
            driver.get(building_url)
            WebDriverWait(driver, 25).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, 'input[name="quantity"]')
            )
            self.errors = []
            self.building_busy = 'building is currently busy' in driver.find_element(
                By.TAG_NAME, 'body'
            ).text.casefold()
            recommendations = []
            seen_products = set()
            for quantity_input in self._quantity_inputs(driver):
                card = self._product_card(driver, quantity_input)
                if card is None:
                    continue
                headings = card.find_elements(By.CSS_SELECTOR, 'h3')
                product = headings[0].text.strip() if headings else None
                if not product or product in seen_products:
                    continue
                seen_products.add(product)
                try:
                    recommendation = self._analyse_card(driver, card, product)
                except Exception as error:
                    self.errors.append(f'{product}: {type(error).__name__}')
                    self.logger.warning('[RetailProfitAdvisor] %s: %s', product, error)
                    continue
                if recommendation:
                    recommendations.append(recommendation)
                else:
                    self.errors.append(f'{product}: 無法取得完整試算或符合品質要求的交易所供貨')
                time.sleep(1)
            recommendations.sort(key=lambda item: item.net_profit_total, reverse=True)
            self.checked_at = datetime.now().astimezone().isoformat(timespec='seconds')
            if not recommendations:
                self.logger.warning(
                    "[RetailProfitAdvisor] No retail cards were recognised on %s. "
                    "The SimCompanies UI selectors may need updating.", building_url
                )
            return recommendations
        except Exception as error:  # Notification must still be sent on a parse failure.
            self.logger.warning("[RetailProfitAdvisor] Could not analyse %s: %s", building_url, error)
            return []

    def _quantity_inputs(self, driver) -> list[WebElement]:
        return driver.find_elements(By.CSS_SELECTOR, 'input[name="quantity"]')

    def _legacy_quantity_inputs(self, driver) -> list[WebElement]:
        matches = []
        for element in driver.find_elements(By.CSS_SELECTOR, "input:not([type='hidden'])"):
            descriptor = " ".join(
                filter(
                    None,
                    [
                        element.get_attribute("name"),
                        element.get_attribute("id"),
                        element.get_attribute("aria-label"),
                        element.get_attribute("placeholder"),
                    ],
                )
            ).casefold()
            if any(word in descriptor for word in ("quantity", "amount", "數量")):
                matches.append(element)
        # Current SimCompanies retail cards do not always expose input names.
        # In that case the first editable control in a card is Quantity.
        if not matches:
            matches = driver.find_elements(By.CSS_SELECTOR, "input:not([type='hidden'])")
        return matches

    def _product_card(self, driver, quantity_input: WebElement) -> Optional[WebElement]:
        return driver.execute_script(
            """
            let node = arguments[0];
            while (node && node !== document.body) {
              const text = (node.innerText || '').toLowerCase();
              const controls = node.querySelectorAll('input:not([type=hidden])').length;
              if (controls >= 2 && node.querySelectorAll('input[name="quantity"]').length === 1
                  && node.querySelector('a[href*="/resource/"]')
                  && /average price|profit per unit/.test(text)) {
                return node;
              }
              node = node.parentElement;
            }
            return null;
            """,
            quantity_input,
        )

    def _product_name(self, card_text: str) -> Optional[str]:
        normalised_card = _normalise(card_text)
        candidates = [name for name in self.product_ids if name and name in normalised_card]
        return max(candidates, key=len) if candidates else None

    def _analyse_card(self, driver, card: WebElement, product: str) -> Optional[RetailRecommendation]:
        inputs = card.find_elements(By.CSS_SELECTOR, "input:not([type='hidden'])")
        if len(inputs) < 2:
            return None
        quantity_input = self._pick_input(inputs, ("quantity", "amount", "數量"), fallback=0)
        price_input = self._pick_input(inputs, ("price", "價格"), fallback=1)
        average_price = parse_labeled_number(card.text, ("Average price", "Avg price", "平均價格"))
        if average_price is None:
            self.logger.info("[RetailProfitAdvisor] %s has no average price; skipped.", product)
            return None

        # This only changes the browser's unsaved form state.  No button is
        # clicked, so it cannot start a sale or purchase resources.
        self._set_input_value(driver, quantity_input, f"{self.hours}hr")
        self._set_input_value(driver, price_input, self._number_for_input(average_price))
        WebDriverWait(driver, 10).until(lambda d: 'Profit per unit' in card.text)

        # Duration remains literally "48hr" in the input. The adjacent
        # up/down controls reveal its computed integer quantity, net +0 units.
        if 'hr' in (quantity_input.get_attribute('value') or '').lower():
            parent = quantity_input.find_element(By.XPATH, '..')
            parent.find_element(By.CSS_SELECTOR, 'svg[data-icon="chevron-up"]').click()
            parent.find_element(By.CSS_SELECTOR, 'svg[data-icon="chevron-down"]').click()

        card_text = card.text
        quantity = self._resolved_quantity(quantity_input, card_text)
        retail_profit = parse_labeled_number(
            card_text, ("Profit per unit", "每單位利潤", "每单位利润")
        )
        if quantity is None or retail_profit is None:
            self.logger.info("[RetailProfitAdvisor] %s did not expose calculated quantity/profit.", product)
            return None
        quality = len(card.find_elements(By.CSS_SELECTOR,
            'a[href*="/resource/"] svg[data-icon="star"]'))
        resource_id = self._resource_id_from_card(card)
        # Read the game's own breakdown to account for warehouse COGS and
        # retain the extra precision hidden by the rounded headline profit.
        card.find_element(By.XPATH,
            ".//div[contains(text(), 'Profit per unit')]/button[@aria-label='Help']").click()
        close = WebDriverWait(driver, 10).until(lambda d: d.find_element(
            By.CSS_SELECTOR, 'button[aria-label="Close modal - Retailing breakdown"]'))
        try:
            breakdown = self._read_retailing_breakdown(driver, close)
            # Negative costs are displayed as "(-) $...".
            book_cost = abs(breakdown['COGS'])
            retail_profit = breakdown['Revenue'] - abs(breakdown['Wages']) - book_cost
        finally:
            close.click()
        exchange_price = self._exchange_price(resource_id, quantity, quality)
        if exchange_price is None:
            self.logger.info("[RetailProfitAdvisor] %s lacks enough exchange supply for %.0f units.", product, quantity)
            return None
        return RetailRecommendation(
            product=product.title(),
            quantity=quantity,
            quality=quality,
            retail_profit_per_unit=retail_profit,
            exchange_cost_per_unit=exchange_price,
            inventory_cost_per_unit=book_cost,
            retail_price=breakdown['Revenue'],
            average_retail_price=average_price,
        )

    @staticmethod
    def _read_retailing_breakdown(driver, close_button: WebElement) -> dict[str, float]:
        """Read the breakdown table from the modal opened by this product card.

        SimCompanies renders the help modal outside the retail card in the
        page-level overlay. Start at its close button and walk upward to the
        nearest ancestor containing all expected rows, rather than searching
        inside the card that opened it.
        """
        rows = driver.execute_script(
            """
            let node = arguments[0];
            while (node && node !== document.body) {
              const rows = Array.from(node.querySelectorAll('tr')).map(row =>
                Array.from(row.querySelectorAll('td')).map(cell => (cell.innerText || '').trim())
              );
              const labels = new Set(rows.filter(cells => cells.length >= 2).map(cells => cells[0]));
              if (['Revenue', 'Wages', 'COGS'].every(label => labels.has(label))) return rows;
              node = node.parentElement;
            }
            return [];
            """,
            close_button,
        ) or []
        breakdown = {}
        for cells in rows:
            if len(cells) >= 2 and cells[0] in ('Revenue', 'Wages', 'COGS'):
                breakdown[cells[0]] = parse_number(cells[1])
        if set(breakdown) != {'Revenue', 'Wages', 'COGS'} or any(
            value is None for value in breakdown.values()
        ):
            raise ValueError('Incomplete retailing breakdown')
        return breakdown

    @staticmethod
    def _pick_input(inputs, words: tuple[str, ...], fallback: int) -> WebElement:
        for item in inputs:
            descriptor = " ".join(
                filter(None, [item.get_attribute("name"), item.get_attribute("id"), item.get_attribute("aria-label")])
            ).casefold()
            if any(word in descriptor for word in words):
                return item
        return inputs[fallback]

    @staticmethod
    def _set_input_value(driver, element: WebElement, value: str) -> None:
        element.send_keys(Keys.CONTROL, 'a')
        element.send_keys(value, Keys.TAB)

    @staticmethod
    def _number_for_input(value: float) -> str:
        return f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _quality(text: str) -> int:
        match = re.search(r"\bQ\s*(\d+)\b", text, re.IGNORECASE)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _resource_id_from_card(card: WebElement) -> Optional[int]:
        """Prefer the resource id rendered in the card over a local product list."""
        for link in card.find_elements(By.CSS_SELECTOR, "a[href]"):
            match = re.search(r"/(?:market|encyclopedia/\d+)/resource/(\d+)/", link.get_attribute("href") or "")
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _resolved_quantity(quantity_input: WebElement, card_text: str) -> Optional[float]:
        input_value = quantity_input.get_attribute("value") or ""
        if not re.search(r"(?:hr|hour|小時|小时)", input_value, re.IGNORECASE):
            parsed = parse_number(input_value)
            if parsed and parsed > 0:
                return parsed
        # Do not mistake the literal calculator input (``48hr``) for 48
        # saleable units.  If the UI leaves the duration visible, only accept
        # a separate numeric total rendered by the card.
        for label in ("Total quantity", "Quantity", "總數量", "总数量"):
            match = re.search(
                rf"{re.escape(label)}\s*:?\s*({_NUMBER_PATTERN})",
                card_text,
                re.IGNORECASE,
            )
            if not match:
                continue
            suffix = card_text[match.end():]
            if re.match(r"\s*(?:hr|hour|小時|小时)", suffix, re.IGNORECASE):
                continue
            parsed = parse_number(match.group(1))
            if parsed and parsed > 0:
                return parsed
        return None

    def _exchange_price(self, resource_id: Optional[int], quantity: float, quality: int) -> Optional[float]:
        if resource_id is None:
            return None
        try:
            response = self.session.get(
                MARKET_URL.format(realm=self.realm, resource_id=resource_id), timeout=20
            )
            response.raise_for_status()
            orders = response.json()
            if not isinstance(orders, list):
                return None
            # The exchange can source at least the preview quality. Keep the
            # preview's sales speed: do not invent extra capacity for any
            # higher-quality units in the batch, and disclose this basis.
            orders = [o for o in orders if not o.get('blocked')]
            return weighted_market_price(orders, quantity, quality)
        except (requests.RequestException, ValueError) as error:
            self.logger.warning("[RetailProfitAdvisor] Exchange lookup for %s failed: %s", resource_id, error)
            return None

    @staticmethod
    def telegram_text(recommendations: list[RetailRecommendation], hours: int) -> str:
        if not recommendations:
            return ""
        lines = [f"📊 約 {hours} 小時零售淨利比較（即時試算）",
                 '依頁面 Average price 試算；按同品質或更高品質的整批交易所補貨成本比較。']
        for rank, item in enumerate(recommendations, start=1):
            lines.append(
                f"\n{rank}. {item.product} Q{item.quality}｜{item.quantity:,.0f} 件\n"
                f"零售價 ${item.retail_price:,.2f}｜交易所加權 ${item.exchange_cost_per_unit:,.2f}/件\n"
                f"淨利 ${item.net_profit_total:,.0f}（${item.net_profit_per_unit:,.2f}/件）"
            )
        lines.append('\n已按成本明細計入工資；庫存帳面成本先加回，再換成市價，避免重複扣除。')
        lines.append('Q 為目前頁面試算品質；若補貨取得更高品質，未額外計入其銷售加速。金額為依即時資料估算，未來行情可能改變。')
        return "\n".join(lines)
