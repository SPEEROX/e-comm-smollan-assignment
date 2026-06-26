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


## How it's built

- Most CSS selectors have a backup selector listed right after them, so if the main one stops matching (site redesign, A/B test, whatever), there's a fallback instead of the script just dying.
- Every field is wrapped in a `try`-style helper (`get_text_safe`, `get_attribute_safe`) that returns `None` and adds a message to that record's `errors` list instead of crashing the whole script if something can't be found.
- Anywhere clicking a button might re-render the page (storage options, color swatches), the code re-finds the elements fresh on every loop step instead of reusing old references, since clicking can make Selenium's old element reference "stale."
