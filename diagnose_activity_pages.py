"""Read the live building-page activity markup without changing game state."""

import json
import os
import re
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from production_monitor import BuildingConstructionMonitor, setup_logger


KEYWORDS = ("finish", "construction", "complete", "build", "upgrade")


def relevant_text(driver):
    """Return visible activity-related text from likely UI elements."""
    texts = driver.execute_script(
        "return Array.from(document.querySelectorAll('h1,h2,h3,h4,p,button,span,div'))"
        ".map(element => (element.innerText || '').trim())"
        ".filter(Boolean);"
    )
    return list(dict.fromkeys(
        text for text in texts if any(keyword in text.casefold() for keyword in KEYWORDS)
    ))


def main():
    logger = setup_logger("activity_dom_diagnostic", "activity_dom_diagnostic.log")
    monitor = BuildingConstructionMonitor(
        logger=logger,
        user_data_dir=os.getenv("USER_DATA_DIR_construction_monitor"),
    )
    try:
        if not monitor._initialize_driver():
            return 1
        paths = monitor._get_landscape_building_paths()
        if paths is None:
            return 1
        start = int(os.getenv("ACTIVITY_DIAGNOSTIC_START", "0"))
        limit = int(os.getenv("ACTIVITY_DIAGNOSTIC_LIMIT", str(len(paths))))
        selected_paths = paths[start:start + limit]
        report = []
        for path in selected_paths:
            url = monitor.base_url + path
            monitor.driver.get(url)
            WebDriverWait(monitor.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            # SimCompanies is a client-rendered SPA.  A present <body> and a
            # completed document state are not enough: wait for its actual
            # visible page content before examining activity controls.
            try:
                WebDriverWait(monitor.driver, 20, poll_frequency=0.2).until(
                    lambda driver: (
                        (body_text := driver.execute_script("return document.body.innerText || ''")).strip()
                        and "fetching building info" not in body_text.casefold()
                    )
                )
            except Exception:
                logger.warning("Building details did not load within 20 seconds: %s", path)
            headings = monitor.driver.execute_script(
                "return Array.from(document.querySelectorAll('h1,h2,h3,h4'))"
                ".map(element => (element.innerText || '').trim()).filter(Boolean);"
            )
            finish_nodes = monitor.driver.execute_script(
                "return Array.from(document.querySelectorAll('p,div,span'))"
                ".filter(element => (element.innerText || '').trim().toLowerCase().includes('finishes at'))"
                ".map(element => ({tag: element.tagName.toLowerCase(), text: element.innerText.trim(), html: element.outerHTML}));"
            )
            report.append({
                "path": path,
                "url": url,
                "loaded_url": monitor.driver.current_url,
                "body_text_length": len(monitor.driver.execute_script("return document.body.innerText || ''") or ""),
                "headings": headings,
                "finish_nodes": finish_nodes,
                "activity_related_text": relevant_text(monitor.driver),
            })
        output_path = os.path.join("record", f"activity_dom_diagnostic_{start}.json")
        with open(output_path, "w", encoding="utf-8") as report_file:
            json.dump(report, report_file, ensure_ascii=False, indent=2)
        print(f"Saved live DOM diagnostic for {len(report)} buildings to {output_path}")
        return 0
    finally:
        monitor._quit_driver()


if __name__ == "__main__":
    sys.exit(main())
