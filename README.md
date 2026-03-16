# Bumble Auto-Swipe

A Tampermonkey userscript that automatically swipes on the Bumble web app.

## Install

1. Install the [Tampermonkey](https://www.tampermonkey.net/) browser extension.
2. Open Tampermonkey → **Create new script**.
3. Paste the contents of `bumble-autoswipe.user.js` (or drag-and-drop the file into Tampermonkey's dashboard to auto-install).
4. Save and navigate to **https://bumble.com/app**.

## Usage

A floating panel appears in the bottom-right corner:

| Control | Description |
|---|---|
| **▶ Start Auto-Swipe** | Begin swiping |
| **⏸ Stop** | Pause |
| **Alt + S** | Keyboard toggle |
| **Like ratio** slider | Fraction of profiles to like (default 85 %) |
| **Min / Max delay** sliders | Random wait between swipes (default 1.8 – 3.5 s) |
| Stats badge | Running count of likes `L` and passes `P` |

## How it works

- Finds the visible **Like** or **Pass** button using Bumble's `data-qa-role` attributes and CSS classes.
- Fires `mousedown` → `mouseup` → `click` events to simulate a real click.
- Automatically dismisses modals (upsell popups, "It's a Match!" screens) before continuing.
- Randomises delay between swipes to avoid bot-detection patterns.

## Notes

- Works on the **Bumble web app** (`bumble.com/app`).
- Free accounts have a daily swipe limit – the script will pause when the limit popup appears (it cannot bypass Bumble's server-side limits).
- Selectors may need updating if Bumble ships a major front-end redesign. The relevant arrays are `SEL.like`, `SEL.dislike`, and `SEL.dismiss` near the top of the script.
