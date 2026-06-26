#!/usr/bin/env python3
"""
Selenium scraper for two assignments:
  1. Verizon smartphones listing page -> outputs/verizon_listing.json
  2. T-Mobile phone PDPs (from a urls file) -> outputs/tmobile_pdp.json

Usage:
    python assignment.py verizon --listing-url https://www.verizon.com/smartphones/ --limit 8
    python assignment.py tmobile --urls tmobile_urls.txt
"""

import argparse
import json
import logging
import os
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    WebDriverException,
)

# --------------------------------------------------------------------------
# Basic config / constants
# --------------------------------------------------------------------------

OUTPUT_DIR = "outputs"
SCREENSHOT_DIR = "screenshots"
DEFAULT_WAIT = 15
SHORT_WAIT = 5

# ---- Verizon selectors ----
VERIZON_CARD_SELECTORS = [
    (By.CSS_SELECTOR, "[data-testid='product-tile']"),
    (By.CSS_SELECTOR, "div[class*='product-tile']"),
]
VERIZON_NAME_SELECTORS = [
    (By.CSS_SELECTOR, "#gridwallProductName"),
    (By.CSS_SELECTOR, "h2 a"),
]
VERIZON_LINK_SELECTORS = [
    (By.CSS_SELECTOR, "#gridwallProductName a"),
    (By.CSS_SELECTOR, "a[href*='/smartphones/']"),
]
VERIZON_IMAGE_SELECTORS = [
    (By.CSS_SELECTOR, "img[data-analyticstrack='gridwall-product-image']"),
    (By.CSS_SELECTOR, "img"),
]
VERIZON_PRICE_SELECTORS = [
    (By.CSS_SELECTOR, "[data-testid='trade-in-price']"),
    (By.CSS_SELECTOR, "[data-testid='dpp-frp']"),
    (By.CSS_SELECTOR, "[data-testid='pricing']"),
]
VERIZON_PRICE_STORAGE = [(By.CSS_SELECTOR, "p.VDS__RSC__title-module__2No8x")]
VERIZON_NEXT_PAGE_SELECTORS = [
    (By.CSS_SELECTOR, "a[aria-label='Go to next page.']"),
]
# Rating and storage are PDP-only on Verizon - confirmed from the real
# PDP HTML I was given. They don't exist on the listing cards at all.
VERIZON_PDP_RATING_SELECTORS = [
    (By.CSS_SELECTOR, "a[data-testid='review-click']"),
    (By.CSS_SELECTOR, "[data-qa='shared-starReview-link']"),
]
VERIZON_PDP_STORAGE_GROUP_SELECTORS = [
    (By.CSS_SELECTOR, "[data-testid='storage-group']"),
    (By.CSS_SELECTOR, "[role='radiogroup'][aria-label='Storage']"),
]
VERIZON_PDP_STORAGE_RADIO_SELECTOR = "input[data-testid='radio-box']"
VERIZON_PDP_COLOR_GROUP_SELECTORS = [
    (By.CSS_SELECTOR, "[data-testid='color-group']"),
    (By.CSS_SELECTOR, "[role='radiogroup'][aria-label='Color']"),
]

VERIZON_PDP_COLOR_SELECTOR = "input[type='radio']"

# ---- T-Mobile selectors ----
TMOBILE_NAME_SELECTORS = [
    (By.CSS_SELECTOR, "h1.upf-headline__title"),
]
TMOBILE_BRAND_SELECTORS = [
    (By.CSS_SELECTOR, "[itemprop='brand']"),
    (By.CSS_SELECTOR, ".upf-product-manufacturer"),
]
TMOBILE_AVAILABILITY_SELECTORS = [
    (By.CSS_SELECTOR, ".upf-inventory-status-title"),
    (
        By.XPATH,
        "//*[contains(text(),'In Stock') or contains(text(),'In stock') or contains(text(),'Out of stock')]",
    ),
]
# Storage radios live inside the "pay monthly" tab panel. Each radio's
# whole block (label) has the capacity AND that capacity's monthly price
# AND its full price all together - so we read all three from one block
# instead of clicking then hunting for the price somewhere else on the page.
TMOBILE_STORAGE_FIELDSET_SELECTORS = [
    (
        By.CSS_SELECTOR,
        "#pay-monthly-tabpanel fieldset[aria-label='Storage and payments']",
    ),
    (By.CSS_SELECTOR, "fieldset[aria-label='Storage and payments']"),
]
TMOBILE_STORAGE_BLOCK_SELECTOR = "div.tdds-styled-radio"
TMOBILE_STORAGE_CAPACITY_LABEL_SELECTOR = "label.tdds-styled-radio__container"
TMOBILE_COLOR_FIELDSET_SELECTORS = [
    (By.CSS_SELECTOR, "fieldset.upf-skuSelector__group--color"),
    (By.CSS_SELECTOR, "fieldset[class*='color']"),
]
TMOBILE_PROMO_TRIGGER_SELECTORS = [
    (By.CSS_SELECTOR, "button.upf-productCard__promo--action"),
]
# The actual modal wrapper + close button, taken from the real popup markup.
TMOBILE_PROMO_MODAL_SELECTORS = [
    (By.CSS_SELECTOR, ".upf-productPromoDetails"),
    (By.CSS_SELECTOR, "div.phx-modal__dialog"),
]
TMOBILE_PROMO_CLOSE_SELECTORS = [
    (By.CSS_SELECTOR, "button.phx-modal__close"),
    (By.CSS_SELECTOR, "[aria-label='Close modal.']"),
]
TMOBILE_PROMO_CARD_WAIT_SELECTOR = (
    By.CSS_SELECTOR,
    "article.upf-productPromoDetails__card",
)
TMOBILE_PROMO_CARD_SELECTOR = "article.upf-productPromoDetails__card"
TMOBILE_PROMO_TITLE_SELECTOR = ".upf-productPromoDetails__card--title"
TMOBILE_PROMO_DESC_SELECTOR = ".upf-productPromoDetails__card--description"
TMOBILE_COOKIE_BUTTON_SELECTORS = [
    (By.CSS_SELECTOR, "#onetrust-accept-btn-handler"),
]


# Logging setup


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("assignment")


log = setup_logging()


# Generic helper functions (used by both scrapers)


def make_driver(headless=True):
    """Create and return a Chrome webdriver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver


def find_first(root, selector_list, wait_seconds=DEFAULT_WAIT, many=False):
    """
    Try each (By, selector) pair in selector_list until one of them
    finds an element (or, if many=True, at least one matching element,
    returning the full list). Returns the element / list of elements,
    or None if nothing matched within the timeout.
    """
    for by, selector in selector_list:
        try:
            wait = WebDriverWait(root, wait_seconds)
            if many:
                condition = EC.presence_of_all_elements_located((by, selector))
            else:
                condition = EC.presence_of_element_located((by, selector))
            element = wait.until(condition)
            return element
        except (TimeoutException, NoSuchElementException):
            continue
    return None


def find_all(root, selector_list):
    """
    Try each (By, selector) pair and return the first non-empty list of
    matching elements found inside root. Returns [] if none match.
    This does NOT wait - it's meant to be used after we already know
    the parent container exists.
    """
    for by, selector in selector_list:
        try:
            elements = root.find_elements(by, selector)
            if elements:
                return elements
        except WebDriverException:
            continue
    return []


def get_text_safe(root, selector_list, errors, field_name, wait_seconds=DEFAULT_WAIT):
    """
    Find an element using the selector list and return its stripped text.
    If nothing is found, append a message to the errors list and return None
    instead of crashing the whole script.
    """
    element = find_first(root, selector_list, wait_seconds)
    if element is None:
        errors.append("Could not find element for '{}'".format(field_name))
        return None
    try:
        text = element.text.strip()
        if not text:
            text = (element.get_attribute("content") or "").strip()
        if not text:
            errors.append("Element for '{}' found but had no text".format(field_name))
            return None
        return text
    except StaleElementReferenceException:
        errors.append("Element for '{}' went stale".format(field_name))
        return None


def get_attribute_safe(
    root, selector_list, attribute, errors, field_name, wait_seconds=DEFAULT_WAIT
):
    """Same idea as get_text_safe but for grabbing an HTML attribute (like href, src, or aria-label)."""
    element = find_first(root, selector_list, wait_seconds)
    if element is None:
        errors.append("Could not find element for '{}'".format(field_name))
        return None
    try:
        value = element.get_attribute(attribute)
        if not value:
            errors.append(
                "Element for '{}' had no '{}' attribute".format(field_name, attribute)
            )
            return None
        return value.strip()
    except StaleElementReferenceException:
        errors.append("Element for '{}' went stale".format(field_name))
        return None


def find_first_visible(root, selector_list, wait_seconds=DEFAULT_WAIT):
    """
    Same as find_first, but requires the element to actually be visible
    (not just present in the DOM). Needed for Alpine.js-driven UI where
    x-show toggles display:none rather than removing the element -
    clicking a "present but hidden" element either fails outright or
    silently does nothing.
    """
    for by, selector in selector_list:
        try:
            wait = WebDriverWait(root, wait_seconds)
            element = wait.until(EC.visibility_of_element_located((by, selector)))
            return element
        except (TimeoutException, NoSuchElementException):
            continue
    return None


def safe_click(driver, element):
    """
    Click an element, scrolling it into view first. If a normal click
    gets blocked by something covering the element, fall back to a JS
    click. Returns True/False depending on whether it worked.
    """
    if element is None:
        return False
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        time.sleep(0.3)
        try:
            element.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", element)
        return True
    except (StaleElementReferenceException, WebDriverException) as exc:
        log.warning("Click failed: %s", exc)
        return False


def dismiss_cookie_banner(driver):
    """Click the cookie-accept button if it shows up. Not a big deal if it doesn't."""
    banner = find_first(driver, TMOBILE_COOKIE_BUTTON_SELECTORS, wait_seconds=3)
    if banner:
        safe_click(driver, banner)


def save_screenshot(driver, filename):
    """Save a screenshot into the screenshots/ folder. Returns the path, or None on failure."""
    if not os.path.exists(SCREENSHOT_DIR):
        os.makedirs(SCREENSHOT_DIR)
    path = os.path.join(SCREENSHOT_DIR, filename)
    try:
        driver.save_screenshot(path)
        log.info("Saved screenshot: %s", path)
        return path
    except WebDriverException as exc:
        log.warning("Could not save screenshot %s: %s", filename, exc)
        return None


def write_json(data, filename):
    """Write a dict/list to outputs/<filename> as pretty JSON."""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Wrote output: %s", path)


def normalize_price(price_text):
    """Pull a plain float out of a price string like '$799.99/mo' so prices can be compared."""
    if not price_text:
        return None
    match = re.search(r"[\d,]+\.\d{2}", price_text)
    if not match:
        match = re.search(r"\d+", price_text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def is_iphone_17(name):
    """Check if a product name refers to an iPhone 17 (any variant)."""
    if not name:
        return False
    return "iphone 17" in name.lower()


# Verizon scraping logic


def scrape_verizon_card(card):
    """Pull the listing-card-level fields out of a single product card element.
    Rating and storage are NOT here - they only exist on the PDP, see
    scrape_verizon_pdp_extra() below."""
    product = {
        "product_name": None,
        "product_url": None,
        "monthly_price": None,
        "rating": None,
        "storage_variants": [],
        "visible_colours": None,
        "is_iphone_17": False,
        "found_via": "listing_grid",
        "errors": [],
    }
    errors = product["errors"]

    product["product_name"] = get_text_safe(
        card, VERIZON_NAME_SELECTORS, errors, "product_name", wait_seconds=1
    )
    product["product_url"] = get_attribute_safe(
        card, VERIZON_LINK_SELECTORS, "href", errors, "product_url", wait_seconds=1
    )
    # product["image_url"] = get_attribute_safe(
    #     card, VERIZON_IMAGE_SELECTORS, "src", errors, "image_url", wait_seconds=3
    # )
    product["monthly_price"] = get_text_safe(
        card, VERIZON_PRICE_SELECTORS, errors, "monthly_price", wait_seconds=1
    )
    product["is_iphone_17"] = is_iphone_17(product["product_name"])

    return product


def scrape_verizon_pdp_extra(driver, product):
    """
    Visit a product's PDP and fill in the fields that only exist there:
    rating and storage variants (with per-variant price).

    Rating is read from the aria-label of the review link, e.g.
    "4.4 out of 5 rating (7.2K reviews)" - we keep that whole string as
    the rating value since it's more informative than just the number.

    Storage variants are read by clicking each radio button in the
    storage group one at a time and re-reading the price after each
    click, since on Verizon's PDP the price block updates to reflect
    whichever storage size is currently selected.
    """
    errors = product["errors"]

    rating_text = get_attribute_safe(
        driver,
        VERIZON_PDP_RATING_SELECTORS,
        "aria-label",
        errors,
        "rating",
        wait_seconds=SHORT_WAIT,
    )
    product["rating"] = rating_text

    storage_group = find_first(
        driver, VERIZON_PDP_STORAGE_GROUP_SELECTORS, wait_seconds=SHORT_WAIT
    )
    if storage_group is None:
        # Not every product necessarily has a storage choice (e.g. accessories
        # that snuck into the grid) so this isn't always a real error.
        return

    radios = storage_group.find_elements(
        By.CSS_SELECTOR, VERIZON_PDP_STORAGE_RADIO_SELECTOR
    )
    if not radios:
        return

    variants = []
    for i in range(len(radios)):
        # re-find fresh each time in case clicking re-renders the storage group
        fresh_group = find_first(
            driver, VERIZON_PDP_STORAGE_GROUP_SELECTORS, wait_seconds=3
        )
        if fresh_group is None:
            break
        fresh_radios = fresh_group.find_elements(
            By.CSS_SELECTOR, VERIZON_PDP_STORAGE_RADIO_SELECTOR
        )
        if i >= len(fresh_radios):
            break

        radio = fresh_radios[i]
        storage_value = (radio.get_attribute("value") or "").strip()

        clicked = safe_click(driver, radio)
        if not clicked:
            errors.append(
                "Could not click storage option '{}'".format(storage_value or i)
            )
            continue

        price_el = find_first(driver, VERIZON_PRICE_STORAGE, wait_seconds=3)
        price_text = price_el.text.strip() if price_el else None
        variants.append({"storage": storage_value or None, "price": price_text})

    product["storage_variants"] = variants

    color_group = find_first(
        driver,
        VERIZON_PDP_COLOR_GROUP_SELECTORS,
        wait_seconds=SHORT_WAIT,
    )

    if color_group is None:
        return

    colors = color_group.find_elements(
        By.CSS_SELECTOR,
        VERIZON_PDP_COLOR_SELECTOR,
    )

    if not colors:
        return

    visible_colours = []

    for color in colors:
        colour_name = (color.get_attribute("aria-label") or "").strip()

        if colour_name.startswith("Color"):
            colour_name = colour_name.replace("Color", "", 1).strip()

        if "out of stock" in colour_name.lower():
            colour_name = (
                colour_name.replace("out of stock", "")
                .replace("Out of stock", "")
                .strip()
            )

        visible_colours.append(colour_name)

    product["visible_colours"] = visible_colours


def go_to_next_verizon_page(driver):
    """Click the 'next page' link if it's there. Returns True if it clicked something."""
    next_link = find_first(driver, VERIZON_NEXT_PAGE_SELECTORS, wait_seconds=3)
    if next_link is None:
        return False
    return safe_click(driver, next_link)


def search_all_pages_for_iphone17(driver, max_pages=6):
    """
    If iPhone 17 wasn't in the first batch of products, page through the
    listing looking for it. Returns a product dict or None.
    """
    log.info("iPhone 17 not in first batch - searching remaining pages")
    for page_num in range(max_pages):
        cards = find_all(driver, VERIZON_CARD_SELECTORS)
        for card in cards:
            try:
                name_el = find_first(card, VERIZON_NAME_SELECTORS, wait_seconds=2)
                name_text = name_el.text.strip() if name_el else ""
            except StaleElementReferenceException:
                continue
            if is_iphone_17(name_text):
                product = scrape_verizon_card(card)
                product["found_via"] = "explicit_search"
                return product
        moved = go_to_next_verizon_page(driver)
        if not moved:
            break
        time.sleep(1.5)
    return None


def rating_color_storage(driver, products):
    """
    Visit every Verizon PDP and populate rating,
    visible colours and storage options.
    """

    for product in products:
        if not product["product_url"]:
            product["errors"].append("No URL available, cannot visit PDP")
            continue

        try:
            driver.get(product["product_url"])
            scrape_verizon_pdp_extra(driver, product)

        except WebDriverException as exc:
            product["errors"].append("Could not load PDP: {}".format(exc))

    return products


def run_verizon(args):
    driver = make_driver(headless=not args.no_headless)
    result = {
        "listing_url": args.listing_url,
        "requested_limit": args.limit,
        "products": [],
        "iphone_17_in_first_n": False,
        "iphone_17_product": None,
        "errors": [],
    }

    try:
        log.info("Opening Verizon listing page: %s", args.listing_url)
        driver.get(args.listing_url)

        cards = find_all(driver, VERIZON_CARD_SELECTORS)
        if not cards:
            result["errors"].append("No product cards found on the listing page")
            save_screenshot(driver, "verizon_listing.png")
            return result

        log.info(
            "Found %d cards on the page, scraping first %d", len(cards), args.limit
        )

        products = []
        seen_urls = set()
        for card in cards:
            if len(products) >= args.limit:
                break
            try:
                product = scrape_verizon_card(card)
            except StaleElementReferenceException:
                continue
            key = product["product_url"] or product["product_name"]
            if not key or key in seen_urls:
                continue
            seen_urls.add(key)
            products.append(product)

        result["products"] = products

        # check for iPhone 17
        found = [p for p in products if p["is_iphone_17"]]
        if found:
            result["iphone_17_in_first_n"] = True
            result["iphone_17_product"] = found[0]
        else:
            result["iphone_17_in_first_n"] = False
            result["iphone_17_product"] = search_all_pages_for_iphone17(driver)
            driver.get(args.listing_url)

        save_screenshot(driver, "verizon_listing.png")

        # stretch goal: visit first 3 PDPs - this also fills in rating
        # and storage_variants for those 3 products, since those fields
        # only exist on the PDP, not the listing card.
        rating_color_storage(driver, products)

    finally:
        driver.quit()

    return result


# T-Mobile scraping logic


def read_urls_file(path):
    """Read one URL per line from a text file, skipping blanks and comments."""
    urls = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    except OSError as exc:
        log.error("Could not read urls file %s: %s", path, exc)
    return urls


def parse_storage_block(block):
    """
    Pull capacity, monthly price, and full price out of ONE storage radio
    block. Everything for a given storage size lives together in the same
    block (parent), so we read all three "child" pieces from that one
    block before moving to the next block - instead of clicking through
    each option and hunting for the price somewhere else on the page.

    Full price comes from the line that looks like "Full price: $X + tax"
    inside the pay-monthly block itself (this is option 1 from the two
    possible approaches - reading it directly is simpler and doesn't
    require switching to the "pay in full" tab at all).
    """
    capacity = None
    monthly_price = None
    full_price = None

    capacity_el = block.find_element(By.CSS_SELECTOR, ".tdds-styled-radio__label")
    capacity = capacity_el.text.strip() or None

    # every ".tdds-styled-radio__label" inside this block, in order:
    # [0] = capacity, [1] = the monthly price line, [2] = "for N months" (skip)
    label_spans = block.find_elements(By.CSS_SELECTOR, ".tdds-styled-radio__label")
    if len(label_spans) >= 2:
        monthly_price = label_spans[1].text.strip() or None

    # "Full price: $X + tax" is one of the ".tdds-styled-radio__body" spans
    body_spans = block.find_elements(By.CSS_SELECTOR, ".tdds-styled-radio__body")
    for span in body_spans:
        text = span.text.strip()
        if text.lower().startswith("full price"):
            full_price = text
            break

    return capacity, monthly_price, full_price


def try_storage_selector(driver, product, errors):
    """
    Go through each storage block (parent), and for each one read its
    own capacity + monthly price + full price together (child fields),
    then move on to the next block. This matches how the page is
    actually built - each block is self-contained.
    """
    interaction = {
        "component": "storage_selector",
        "attempted": False,
        "succeeded": False,
        "errors": [],
    }

    fieldset = find_first(driver, TMOBILE_STORAGE_FIELDSET_SELECTORS, wait_seconds=5)
    if fieldset is None:
        interaction["detail"] = "No storage selector found on this page"
        return interaction, [], None, None, None

    interaction["attempted"] = True
    blocks = fieldset.find_elements(By.CSS_SELECTOR, TMOBILE_STORAGE_BLOCK_SELECTOR)

    storage_options = []
    selected_storage = None
    selected_monthly_price = None
    selected_full_price = None

    for i in range(len(blocks)):
        # re-find fresh in case a previous click re-rendered the fieldset
        fresh_fieldset = find_first(
            driver, TMOBILE_STORAGE_FIELDSET_SELECTORS, wait_seconds=3
        )
        if fresh_fieldset is None:
            break
        fresh_blocks = fresh_fieldset.find_elements(
            By.CSS_SELECTOR, TMOBILE_STORAGE_BLOCK_SELECTOR
        )
        if i >= len(fresh_blocks):
            break
        block = fresh_blocks[i]

        try:
            capacity, monthly_price, full_price = parse_storage_block(block)
        except NoSuchElementException:
            errors.append("Could not read storage block at index {}".format(i))
            continue

        if capacity:
            storage_options.append(capacity)

        # is this block currently the selected one? the radio input has
        # the real "checked" state; the label is what we'd click to select it.
        try:
            radio_input = block.find_element(By.CSS_SELECTOR, "input[type='radio']")
            is_checked = radio_input.is_selected()
        except (NoSuchElementException, StaleElementReferenceException):
            is_checked = False

        if is_checked:
            selected_storage = capacity
            selected_monthly_price = monthly_price
            selected_full_price = full_price

        # click this block's own label so we exercise the dynamic
        # interaction (selecting a different storage option), then
        # immediately re-read THIS block's own values - same parent,
        # before moving on to the next block.
        try:
            label = block.find_element(
                By.CSS_SELECTOR, TMOBILE_STORAGE_CAPACITY_LABEL_SELECTOR
            )
            clicked = safe_click(driver, label)
            if clicked:
                # if this is the block we just clicked, treat it as selected
                selected_storage = capacity
                selected_monthly_price = monthly_price
                selected_full_price = full_price
        except (NoSuchElementException, StaleElementReferenceException):
            errors.append(
                "Could not click storage block for '{}'".format(capacity or i)
            )

    interaction["succeeded"] = len(storage_options) > 0
    interaction["detail"] = "Captured {} storage option(s)".format(len(storage_options))
    return (
        interaction,
        storage_options,
        selected_storage,
        selected_monthly_price,
        selected_full_price,
    )


def try_color_selector(driver, errors):
    """Click through color swatches (if present) and record the available color names."""
    interaction = {
        "component": "color_selector",
        "attempted": False,
        "succeeded": False,
        "errors": [],
    }
    colors = []
    selected_color = None

    fieldset = find_first(driver, TMOBILE_COLOR_FIELDSET_SELECTORS, wait_seconds=5)
    if fieldset is None:
        interaction["detail"] = "No color selector found on this page"
        return interaction, colors, selected_color

    interaction["attempted"] = True
    swatches = fieldset.find_elements(By.CSS_SELECTOR, "label.color-swatch-card")
    if not swatches:
        swatches = fieldset.find_elements(By.TAG_NAME, "label")

    for i in range(len(swatches)):
        fresh_fieldset = find_first(
            driver, TMOBILE_COLOR_FIELDSET_SELECTORS, wait_seconds=3
        )
        if fresh_fieldset is None:
            break
        fresh_swatches = fresh_fieldset.find_elements(
            By.CSS_SELECTOR, "label.color-swatch-card"
        )
        if not fresh_swatches:
            fresh_swatches = fresh_fieldset.find_elements(By.TAG_NAME, "label")
        if i >= len(fresh_swatches):
            break

        swatch = fresh_swatches[i]
        try:
            name_el = swatch.find_element(By.CSS_SELECTOR, ".color-swatch-label")
            name_text = name_el.text.strip()
        except NoSuchElementException:
            name_text = (swatch.get_attribute("aria-label") or "").strip()

        if name_text:
            colors.append(name_text)

        try:
            radio_input = swatch.find_element(By.CSS_SELECTOR, "input[type='radio']")
            if radio_input.is_selected():
                selected_color = name_text
        except (NoSuchElementException, StaleElementReferenceException):
            pass

        clicked = safe_click(driver, swatch)
        if clicked and name_text:
            selected_color = name_text
        elif not clicked:
            errors.append("Could not click color swatch {}".format(i))

    colors = list(dict.fromkeys(colors))
    interaction["succeeded"] = len(colors) > 0
    interaction["detail"] = "Captured {} color(s)".format(len(colors))
    return interaction, colors, selected_color


def try_promotions_modal(driver, errors):
    interaction = {
        "component": "promotions_modal",
        "attempted": False,
        "succeeded": False,
        "errors": [],
    }
    promotions = []

    trigger = find_first_visible(
        driver, TMOBILE_PROMO_TRIGGER_SELECTORS, wait_seconds=5
    )
    if trigger is None:
        interaction["detail"] = "No promotions trigger found on this page"
        return interaction, promotions

    interaction["attempted"] = True
    clicked = safe_click(driver, trigger)
    if not clicked:
        interaction["errors"].append("Could not click promotions trigger")
        return interaction, promotions

    # Wait for an actual visible promo card, not just presence in the DOM -
    # Alpine can render the card markup before its x-show/transition
    # finishes revealing it.
    first_card = find_first_visible(
        driver,
        [(By.CSS_SELECTOR, TMOBILE_PROMO_CARD_SELECTOR)],
        wait_seconds=DEFAULT_WAIT,
    )
    if first_card is None:
        interaction["errors"].append(
            "Clicked promotions trigger but no promo cards became visible"
        )
        return interaction, promotions

    try:
        # now safe to grab the full list - at least one is confirmed visible
        modal = find_first(driver, TMOBILE_PROMO_MODAL_SELECTORS, wait_seconds=3)
        cards = (
            modal.find_elements(By.CSS_SELECTOR, TMOBILE_PROMO_CARD_SELECTOR)
            if modal is not None
            else driver.find_elements(By.CSS_SELECTOR, TMOBILE_PROMO_CARD_SELECTOR)
        )

        for card in cards:
            title_el = card.find_elements(By.CSS_SELECTOR, TMOBILE_PROMO_TITLE_SELECTOR)
            desc_el = card.find_elements(By.CSS_SELECTOR, TMOBILE_PROMO_DESC_SELECTOR)
            title_text = title_el[0].text.strip() if title_el else None
            desc_text = desc_el[0].text.strip() if desc_el else None
            if title_text or desc_text:
                promotions.append(
                    {
                        "title": title_text,
                        "description": desc_text,
                        "source_interaction": "promo_modal",
                    }
                )
        interaction["succeeded"] = len(promotions) > 0
        interaction["detail"] = "Captured {} promo card(s)".format(len(promotions))
    except WebDriverException as exc:
        interaction["errors"].append("Error reading promotions popup: {}".format(exc))

    close_btn = find_first(driver, TMOBILE_PROMO_CLOSE_SELECTORS, wait_seconds=3)
    if close_btn is not None:
        safe_click(driver, close_btn)

    return interaction, promotions


def scrape_tmobile_pdp(driver, url, index):
    """
    Scrape one T-Mobile PDP. Returns a dict matching the requested
    output schema (partner / source_type / source_url / product_name /
    brand / available_colours / available_storage_options /
    selected_colour / selected_storage / monthly_price /
    full_retail_price / promotions / availability_status / errors).
    """
    errors = []
    product = {
        "partner": "tmobile",
        "source_type": "pdp",
        "source_url": url,
        "product_name": None,
        "brand": None,
        "available_colours": [],
        "available_storage_options": [],
        "selected_colour": None,
        "selected_storage": None,
        "monthly_price": None,
        "full_retail_price": None,
        "promotions": [],
        "availability_status": None,
        "errors": errors,
    }

    try:
        log.info("Opening T-Mobile PDP: %s", url)
        driver.get(url)
    except WebDriverException as exc:
        errors.append("Failed to load page: {}".format(exc))
        return product

    dismiss_cookie_banner(driver)

    product["product_name"] = get_text_safe(
        driver, TMOBILE_NAME_SELECTORS, errors, "product_name"
    )
    product["brand"] = get_text_safe(
        driver, TMOBILE_BRAND_SELECTORS, errors, "brand", wait_seconds=5
    )
    product["availability_status"] = get_text_safe(
        driver,
        TMOBILE_AVAILABILITY_SELECTORS,
        errors,
        "availability_status",
        wait_seconds=5,
    )

    # storage selector - block-by-block (parent->child) reading.
    (
        storage_interaction,
        storage_options,
        selected_storage,
        monthly_price,
        full_price,
    ) = try_storage_selector(driver, product, errors)
    product["available_storage_options"] = storage_options
    product["selected_storage"] = selected_storage
    product["monthly_price"] = monthly_price
    product["full_retail_price"] = full_price

    # color selector
    color_interaction, colors, selected_color = try_color_selector(driver, errors)
    product["available_colours"] = colors
    product["selected_colour"] = selected_color

    # promotions modal
    promo_interaction, promotions = try_promotions_modal(driver, errors)
    product["promotions"] = promotions

    # for debugging which dynamic interactions actually fired.
    dynamic_interactions = [storage_interaction, color_interaction, promo_interaction]
    succeeded_count = sum(1 for i in dynamic_interactions if i["succeeded"])
    log.info(
        "Finished PDP '%s': name=%r, %d/%d dynamic interactions succeeded, %d field errors.",
        url,
        product["product_name"],
        succeeded_count,
        len(dynamic_interactions),
        len(errors),
    )

    save_screenshot(driver, "tmobile_pdp_{}.png".format(index))

    return product


def run_tmobile(args):
    driver = make_driver(headless=not args.no_headless)
    result = {"source_file": args.urls, "products": [], "errors": []}

    urls = read_urls_file(args.urls)
    if not urls:
        result["errors"].append("No URLs found in {}".format(args.urls))
        driver.quit()
        return result

    try:
        for i, url in enumerate(urls, start=1):
            try:
                product = scrape_tmobile_pdp(driver, url, i)
            except WebDriverException as exc:
                product = {
                    "partner": "tmobile",
                    "source_type": "pdp",
                    "source_url": url,
                    "product_name": None,
                    "brand": None,
                    "available_colours": [],
                    "available_storage_options": [],
                    "selected_colour": None,
                    "selected_storage": None,
                    "monthly_price": None,
                    "full_retail_price": None,
                    "promotions": [],
                    "availability_status": None,
                    "errors": ["Unhandled error: {}".format(exc)],
                }
            result["products"].append(product)
    finally:
        driver.quit()

    return result


# CLI


def build_parser():
    parser = argparse.ArgumentParser(description="Verizon + T-Mobile phone scraper")
    parser.add_argument(
        "--no-headless", action="store_true", help="show the browser window"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    verizon_parser = subparsers.add_parser(
        "verizon", help="scrape the Verizon listing page"
    )
    verizon_parser.add_argument("--listing-url", required=True)
    verizon_parser.add_argument("--limit", type=int, default=8)

    tmobile_parser = subparsers.add_parser(
        "tmobile", help="scrape T-Mobile PDPs from a file"
    )
    tmobile_parser.add_argument("--urls", required=True)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "verizon":
            if args.limit <= 0:
                log.error("--limit must be a positive number")
                return 1
            result = run_verizon(args)
            write_json(result, "verizon_listing.json")

        elif args.command == "tmobile":
            if not os.path.exists(args.urls):
                log.error("urls file not found: %s", args.urls)
                return 1
            result = run_tmobile(args)
            write_json(result, "tmobile_pdp.json")

        else:
            parser.print_help()
            return 1

    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        return 130
    except Exception as exc:
        log.exception("Something went wrong: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
