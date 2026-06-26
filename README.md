# Verizon + T-Mobile Phone Scraper

A Selenium scraper with two parts:

1. **Verizon** - scrapes the smartphones listing page, grabs the first N products, checks for an iPhone 17, and compares listing price vs. product-page price for the first 3 products.
2. **T-Mobile** - scrapes a list of phone product pages (PDPs), reading the storage options, color options, promotions, and the financing/full-price toggle on each one.

Everything lives in one file, `assignment.py`, to keep things simple.

## Project structure

```
project/
├── assignment.py
├── requirements.txt
├── README.md
├── tmobile_urls.txt
├── debugging_note.md
├── outputs/
└── screenshots/
```

## Setup

You'll need Python 3.9+ and Google Chrome installed on your machine.

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

That's it for dependencies - Selenium 4.6+ comes with "Selenium Manager" built in, which automatically grabs the right chromedriver version for whatever Chrome you have installed, so there's nothing extra to download manually.

## How to run it

**Verizon:**
```bash
python assignment.py verizon --listing-url https://www.verizon.com/smartphones/ --limit 8
```

**T-Mobile:**
```bash
python assignment.py tmobile --urls tmobile_urls.txt
```

`tmobile_urls.txt` already has the two URLs from the assignment in it.

Add `--no-headless` to either command if you want to actually watch the browser do its thing (helpful for checking that clicks are landing where they should):

```bash
python assignment.py verizon --listing-url https://www.verizon.com/smartphones/ --limit 8 --no-headless
```

## What you get

- `outputs/verizon_listing.json` - the scraped Verizon data
- `outputs/tmobile_pdp.json` - the scraped T-Mobile data
- `screenshots/verizon_listing.png` - a screenshot of the listing page
- `screenshots/tmobile_pdp_1.png`, `tmobile_pdp_2.png`, etc - one screenshot per T-Mobile URL

### Sample shape of verizon_listing.json

```json
{
  "listing_url": "https://www.verizon.com/smartphones/",
  "requested_limit": 8,
  "products": [
    {
      "name": "Motorola edge - 2026",
      "url": "https://www.verizon.com/smartphones/motorola-edge-2026/?sku=sku6048563",
      "image_url": "https://ss7.vzw.com/is/image/...",
      "listing_price": "Starts at $14.72/mo",
      "rating": null,
      "storage_variants": [],
      "is_iphone_17": false,
      "found_via": "listing_grid",
      "errors": []
    }
  ],
  "iphone_17_in_first_n": false,
  "iphone_17_product": { "...": "filled in if found via search" },
  "price_comparisons": [
    { "product_name": "...", "listing_price": "...", "pdp_price": "...", "status": "match" }
  ],
  "errors": []
}
```

### Sample shape of tmobile_pdp.json

```json
{
  "source_file": "tmobile_urls.txt",
  "products": [
    {
      "url": "https://www.t-mobile.com/cell-phone/apple-iphone-16-plus",
      "name": "iPhone 16 Plus",
      "rating": null,
      "storage_variants": [
        { "storage": "128GB", "price": "..." }
      ],
      "available_colors": ["Black", "White", "Pink"],
      "promotions": ["Get up to $1,000 off with eligible trade-in"],
      "financing_price": "...",
      "full_price": "...",
      "dynamic_interactions": [
        { "component": "storage_selector", "attempted": true, "succeeded": true },
        { "component": "color_selector", "attempted": true, "succeeded": true }
      ],
      "screenshot_path": "screenshots/tmobile_pdp_1.png",
      "errors": []
    }
  ],
  "errors": []
}
```

(Real prices/colors will obviously depend on what's actually showing on the page when it runs - the values above are just to show the shape.)

## How it's built

- Most CSS selectors have a backup selector listed right after them, so if the main one stops matching (site redesign, A/B test, whatever), there's a fallback instead of the script just dying.
- Every field is wrapped in a `try`-style helper (`get_text_safe`, `get_attribute_safe`) that returns `None` and adds a message to that record's `errors` list instead of crashing the whole script if something can't be found.
- Anywhere clicking a button might re-render the page (storage options, color swatches), the code re-finds the elements fresh on every loop step instead of reusing old references, since clicking can make Selenium's old element reference "stale."
- Logging goes to the console so you can see what's happening as it runs.

## Notes / things I'm not 100% sure about

- The selectors were checked against the actual saved HTML I was given for these pages, so I know they match real elements in that snapshot. I wasn't able to run this against a live browser in the environment I built it in (no Chrome installed there), so the very first real run is worth doing with `--no-headless` just to double check the clicks are working the way I expect.
- Verizon's listing cards don't seem to have a star rating element at all, so that field will usually just be `null` - that's expected, not a bug.
- If Verizon or T-Mobile change their page layout significantly, the selectors near the top of `assignment.py` are the first place to go fix things.
