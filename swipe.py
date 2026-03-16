"""
Bumble Auto-Swipe — human-behaviour simulation
Run:  pip install playwright && playwright install chrome
      python swipe.py
"""

import time, random, math
from playwright.sync_api import sync_playwright

# ── Config ────────────────────────────────────────────────────────────────────
LIKE_RATIO   = 0.85   # fraction of profiles to like
CHROME_PROFILE = "/Users/qhungbui7/Library/Application Support/Google/Chrome/Default"

# Timing bands (seconds).  Outlier rows fire rarely but look very human.
# (weight, min, max)
SWIPE_DELAYS = [
    (60, 1.5,  3.0),   # normal fast swipe
    (25, 3.0,  6.0),   # paused to look
    (10, 6.0, 14.0),   # reading bio / scrolling photos
    ( 4, 15., 35.0),   # distracted — long pause
    ( 1, 45., 90.0),   # went for coffee
]
# ─────────────────────────────────────────────────────────────────────────────

# ── Human timing helpers ──────────────────────────────────────────────────────
def human_delay():
    """Pick a delay from the weighted bands above."""
    weights  = [w for w, *_ in SWIPE_DELAYS]
    total    = sum(weights)
    r        = random.uniform(0, total)
    acc      = 0
    for w, lo, hi in SWIPE_DELAYS:
        acc += w
        if r <= acc:
            return random.uniform(lo, hi)
    return random.uniform(1.5, 3.0)

def jitter(base_ms: int, pct: float = 0.25) -> int:
    """Add ±pct random jitter to a millisecond value."""
    spread = int(base_ms * pct)
    return base_ms + random.randint(-spread, spread)

def human_mouse_move(page, x: float, y: float):
    """Move mouse in a curved arc instead of teleporting."""
    cur = page.evaluate("() => ({x: window._mx||0, y: window._my||0})")
    cx, cy = cur.get("x", x), cur.get("y", y)
    steps  = random.randint(8, 18)
    # quadratic bezier control point (random offset)
    cpx = (cx + x) / 2 + random.randint(-80, 80)
    cpy = (cy + y) / 2 + random.randint(-80, 80)
    for i in range(1, steps + 1):
        t  = i / steps
        bx = (1-t)**2*cx + 2*(1-t)*t*cpx + t**2*x
        by = (1-t)**2*cy + 2*(1-t)*t*cpy + t**2*y
        page.mouse.move(bx, by)
        time.sleep(random.uniform(0.01, 0.035))
    page.evaluate(f"() => {{ window._mx={x}; window._my={y}; }}")

def human_click(page, locator):
    """Hover → brief pause → click, with coordinate jitter."""
    box = locator.bounding_box()
    if not box:
        locator.click()
        return
    cx = box["x"] + box["width"]  / 2 + random.uniform(-6, 6)
    cy = box["y"] + box["height"] / 2 + random.uniform(-6, 6)
    human_mouse_move(page, cx, cy)
    time.sleep(random.uniform(0.08, 0.25))   # hover dwell
    page.mouse.down()
    time.sleep(random.uniform(0.05, 0.13))   # hold duration
    page.mouse.up()

# ── Profile viewing simulation ────────────────────────────────────────────────
def get_card_box(page):
    """Return bounding box of the current profile card, or None."""
    for sel in [
        ".encounters-story",
        ".encounters-story-profile",
        ".encounters-story__content",
        ".card",
    ]:
        el = page.locator(sel).first
        if el.is_visible():
            return el.bounding_box()
    return None

def card_tap(page, x, y):
    """Single tap at exact coordinates."""
    human_mouse_move(page, x, y)
    time.sleep(random.uniform(0.06, 0.18))
    page.mouse.down()
    time.sleep(random.uniform(0.04, 0.10))
    page.mouse.up()

def view_profile(page):
    """
    Mirrors Bumble's actual card tap zones:
      top-left  → previous photo
      top-right → next photo
      bottom    → opens expanded profile view (scroll to read, tap bottom again to close)
    """
    box = get_card_box(page)
    if not box:
        time.sleep(random.uniform(0.4, 1.0))
        return

    x0, y0 = box["x"], box["y"]
    w,  h  = box["width"], box["height"]

    # ── Zone helpers ──────────────────────────────────────────────────────────
    def tap_next_photo():
        card_tap(page,
                 x0 + w * random.uniform(0.62, 0.90),
                 y0 + h * random.uniform(0.10, 0.55))

    def tap_prev_photo():
        card_tap(page,
                 x0 + w * random.uniform(0.08, 0.35),
                 y0 + h * random.uniform(0.10, 0.55))

    def tap_bottom():
        """Tap bottom half → opens (or closes) the expanded profile view."""
        card_tap(page,
                 x0 + w * random.uniform(0.20, 0.80),
                 y0 + h * random.uniform(0.62, 0.85))

    # ── Pick a behaviour ──────────────────────────────────────────────────────
    action = random.choices(
        ["glance", "next_photos", "prev_then_next", "open_bio", "photos_then_bio"],
        weights=[25, 30, 10, 20, 15],
    )[0]

    if action == "glance":
        # just look — move mouse across photo area, no click
        human_mouse_move(page,
                         x0 + w * random.uniform(0.2, 0.8),
                         y0 + h * random.uniform(0.15, 0.50))
        time.sleep(random.uniform(0.4, 1.2))

    elif action == "next_photos":
        # tap right side 1–3× to advance through photos
        for _ in range(random.randint(1, 3)):
            tap_next_photo()
            time.sleep(random.uniform(0.7, 2.0))

    elif action == "prev_then_next":
        # go back one photo then forward again (human mistake)
        tap_prev_photo()
        time.sleep(random.uniform(0.5, 1.2))
        tap_next_photo()
        time.sleep(random.uniform(0.5, 1.5))

    elif action == "open_bio":
        # tap bottom half → expanded view opens
        tap_bottom()
        time.sleep(random.uniform(0.6, 1.2))          # wait for it to open
        # scroll down slowly to read bio
        scroll_amount = random.randint(150, 400)
        page.mouse.wheel(0, scroll_amount)
        time.sleep(random.uniform(1.5, 4.5))           # reading time
        # optionally scroll a bit more
        if random.random() < 0.4:
            page.mouse.wheel(0, random.randint(80, 200))
            time.sleep(random.uniform(0.8, 2.0))
        # tap bottom zone again to collapse / return to card
        tap_bottom()
        time.sleep(random.uniform(0.4, 0.9))

    elif action == "photos_then_bio":
        # browse 1–2 photos, then open bio
        for _ in range(random.randint(1, 2)):
            tap_next_photo()
            time.sleep(random.uniform(0.6, 1.6))
        tap_bottom()
        time.sleep(random.uniform(0.6, 1.0))
        page.mouse.wheel(0, random.randint(100, 300))
        time.sleep(random.uniform(1.2, 3.5))
        tap_bottom()
        time.sleep(random.uniform(0.3, 0.7))

# ── Session pacing ────────────────────────────────────────────────────────────
class SessionPacer:
    """
    Every N swipes take a longer break — looks like a real user
    putting their phone down for a bit.
    """
    def __init__(self):
        self.count     = 0
        self.next_break = random.randint(12, 25)

    def tick(self):
        self.count += 1
        if self.count >= self.next_break:
            pause = random.uniform(30, 120)
            print(f"\n  [taking a {pause:.0f}s break…]", flush=True)
            time.sleep(pause)
            self.count      = 0
            self.next_break = random.randint(12, 25)

# ── Main ──────────────────────────────────────────────────────────────────────
liked = passed = 0

def log():
    print(f"\r  liked: {liked:>4}   passed: {passed:>4}   ", end="", flush=True)

with sync_playwright() as p:
    try:
        browser = p.chromium.launch_persistent_context(
            CHROME_PROFILE,
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
    except Exception as e:
        print(f"\n❌  Could not open Chrome profile: {e}")
        print("👉  Close Chrome completely first, then run this script again.\n")
        raise SystemExit(1)

    page = browser.new_page()
    # Track mouse position across calls
    page.evaluate("() => { window._mx = 0; window._my = 0; }")
    page.goto("https://bumble.com/app")

    print("Chrome opened.")
    print("👉  Log in if needed, navigate to the swiping screen.")
    print("    Waiting up to 3 minutes for the Like button…\n")
    page.wait_for_selector(".encounters-action--like", timeout=180_000)
    print("✅  Ready — human-mode swiping started.  Ctrl+C to stop.\n")

    pacer = SessionPacer()

    while True:
        try:
            # ── Dismiss modal / match popup ───────────────────────────────
            for sel in [
                "[data-qa-role='popup-dismiss']",
                "[data-qa-role='match-action-button']",
                ".modal__close-btn",
                "[aria-label='Close']",
            ]:
                el = page.locator(sel).first
                if el.is_visible():
                    time.sleep(random.uniform(0.3, 0.8))
                    human_click(page, el)
                    time.sleep(random.uniform(0.4, 0.9))

            # ── Confirm swipe buttons exist ───────────────────────────────
            like    = page.locator(".encounters-action--like").first
            dislike = page.locator(".encounters-action--dislike").first

            if not like.is_visible() and not dislike.is_visible():
                time.sleep(2)
                continue

            # ── Simulate viewing the profile ──────────────────────────────
            view_profile(page)

            # ── Decide and swipe ──────────────────────────────────────────
            want_like = random.random() < LIKE_RATIO

            if want_like and like.is_visible():
                human_click(page, like)
                liked += 1
            elif dislike.is_visible():
                human_click(page, dislike)
                passed += 1
            else:
                time.sleep(1)
                continue

            log()
            pacer.tick()

            # ── Human-paced delay before next profile ─────────────────────
            time.sleep(human_delay())

        except KeyboardInterrupt:
            print(f"\n\nStopped.  liked={liked}  passed={passed}")
            break
        except Exception:
            time.sleep(1.5)
