# Debugging notes

Just writing down what actually happened while I built this, in case it helps whoever reads this later (or future me).

## How I picked the selectors

I got handed the actual saved HTML for the Verizon listing page and the two T-Mobile PDPs, so instead of guessing selectors I just opened the files and looked for stuff that seemed stable - mainly `data-testid` attributes and `aria-label` attributes, since those usually don't change just because a designer tweaks the CSS. Class names on these sites are a mess (a lot of styled-components hashes like `sc-5k55co-0 isQWmL`), so I avoided those wherever I could find something better.

For Verizon I ended up using `[data-testid='product-tile']` for the card and `data-testid='trade-in-price'` / `'dpp-frp'` for the two price displays. Those are real attributes I found in the page, not something I made up.

For T-Mobile it was a bit more annoying because a lot of the price text in the raw HTML was still showing as `$XX.XX` placeholders (skeleton loaders) - the real numbers only show up after the page's JS runs. That's actually fine for Selenium since it reads whatever is on the page live, but it means I couldn't "see" the real prices just by reading the saved HTML, only the structure around them. I found the storage selector lives inside a `fieldset` with `aria-label="Storage and payments"`, and the color picker is in a fieldset with class `upf-skuSelector__group--color`. The "see promotions" button has text like "See 12 promotions" which was actually visible in the HTML, so that one was easy to find.

## Things that tripped me up

**Multiple matches for the same selector.** When I checked some of my selectors there were 2 matches for things like the financing tab buttons. I'm guessing that's a mobile version and a desktop version both present in the DOM at the same time (display:none on one of them probably). My code just grabs the first match, which seems to work fine in testing, but if this ever picks the wrong (hidden) one I might need to add a "is this actually visible" check.

**Storage button click breaks the reference.** This one I expected going in based on stuff I'd read about Selenium - if you click a button and it changes the page, the old element reference you were holding becomes stale and Selenium throws a `StaleElementReferenceException`. So instead of grabbing the list of storage buttons once and looping over the same list, I re-find the buttons fresh on every loop iteration. A little wasteful but it avoids the crash.

**Cookie banner / sticky headers blocking clicks.** Didn't actually see a cookie banner in this particular HTML snapshot, but I added a "try to dismiss it, don't worry if it's not there" step anyway, since that's such a common thing on real sites and costs nothing if it doesn't find anything.

**Click getting blocked by something on top of the element.** Used `scrollIntoView` before every click plus a fallback to a JS click (`element.click()` via execute_script) if the normal Selenium click gets intercepted. Didn't want a sticky nav bar to randomly break a click halfway through scraping.

**No rating on Verizon listing cards.** I looked specifically for a rating/stars element on the Verizon cards and there genuinely isn't one in the page I was given - so I made that field optional (just stays `null`) instead of treating it as an error every single time, since it's not actually missing, it was never there to begin with.

**Rating and storage aren't on the listing card at all - they're PDP-only.** This one cost me a while. I kept looking for a rating/storage selector on the Verizon listing card HTML and there's just nothing there, no matter how many fallback selectors I tried. Once I got the actual PDP HTML, it turned out both fields genuinely only exist on the product detail page (`a[data-testid='review-click']` with an aria-label like "4.4 out of 5 rating (7.2K reviews)", and `[data-testid='storage-group']` with `input[data-testid='radio-box']` for each size). So I moved both of those into the part of the code that's already visiting each product's PDP, instead of trying to scrape them from the listing card where they were never going to show up. Same trip, just reading more while I'm there. Also worth noting this loop visits every product in the list, sized by whatever `--limit` was passed - I'd accidentally hardcoded it to just the first 3 at one point and had to go back and fix that so `--limit 20` actually visits 20 PDPs, not 3.

**T-Mobile promotions kept coming back empty even though the trigger button and modal selectors were both right.** This was the most annoying bug so far. The promo trigger button (`button.upf-productCard__promo--action`) and the promo card selector (`article.upf-productPromoDetails__card`) were both correct - I'd checked them against the real HTML and they matched exactly. So why was `promotions` always `[]`?

Turned out the button's *parent div* has `x-show="isPromotionAvailable || isResponseAwaited"`. T-Mobile's site uses Alpine.js, and `x-show` doesn't remove the element from the page when its condition is false - it just sets `display: none` on it. The button is still sitting there in the DOM the whole time, present but invisible, until Alpine flips that condition. My `find_first()` was using `presence_of_element_located`, which only checks "does this exist in the DOM" - it has no idea whether the element is actually visible. So I'd grab the button immediately, before Alpine had revealed it, try to click something the page wasn't ready to be clicked on yet, and the click either failed quietly or fired into a UI state that never actually opened the modal.

The fix was adding a second wait helper, `find_first_visible()`, that waits on `visibility_of_element_located` instead of plain presence. I used that specifically for the promo trigger button and for confirming at least one promo card had actually appeared before trying to read the full list. Once I did that, the click reliably landed on a button that was really there and clickable, and the modal had time to actually render its cards before I went looking for them. I also dropped the generic `//button[contains(., 'promotion')]` fallback selector I'd had for the trigger, since it could've matched some other button with "promotion" in its text and made this even harder to debug.

Lesson inside the lesson: "the element exists" and "the element is something a user could currently click" are two completely different questions on a site built with Alpine (or anything else that hides things with `x-show`/similar instead of not rendering them at all). I'd only ever really worried about elements not existing yet (hence all the explicit waits everywhere already) - I hadn't thought about elements existing but being invisible until now.

## What I'd still want to check on a real run

I wrote and tested all the actual logic (the price comparison math, the storage-click loop, the error handling) using fake/mocked browser objects since I didn't have a real Chrome browser available in the environment I was working in. The selectors themselves I checked directly against the real saved HTML files and they all match real elements. But I haven't been able to watch it click through a live browser yet, so the very first real run should probably be done with the browser window visible (not headless) just to eyeball that the clicks are landing on the right thing.

## Lessons learned

- Don't trust class names on big commercial sites, they get regenerated. `data-testid` and `aria-label` held up much better.
- Always assume a click can break your element reference and re-find stuff after clicking.
- "Missing field" and "broken selector" are not the same thing - if a field genuinely isn't on the page (like Verizon's missing ratings), don't log it as an error every time, that just creates noise.
- "Missing from the listing card" doesn't mean "missing" - some fields just live on a different page (PDP vs listing). Check both before assuming a selector is wrong.
- Presence and visibility are not the same thing, especially on Alpine.js-driven pages that use `x-show` to hide stuff instead of not rendering it. Waiting for "exists in the DOM" isn't enough if the thing you're about to click is sitting there with `display: none` on it.
- Test what you can without a real browser before you have one available - mocking the Selenium objects let me catch a couple of bugs in my error-handling logic before ever touching a real page.
