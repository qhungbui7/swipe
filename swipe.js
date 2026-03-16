const { chromium } = require('playwright');
const path = require('path');
const os   = require('os');

// ─── Config ──────────────────────────────────────────────────────────────────
const CONFIG = {
  likeRatio:  0.85,          // fraction of profiles to like (0–1)
  minDelay:   1800,          // ms between swipes (min)
  maxDelay:   3500,          // ms between swipes (max)
  // Uses your real Chrome profile so you're already logged in to Bumble
  userDataDir: path.join(os.homedir(), 'Library/Application Support/Google/Chrome/Default'),
};

// ─── Helpers ─────────────────────────────────────────────────────────────────
const rand  = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const fmt   = (n) => String(n).padStart(4);

// ─── Main ────────────────────────────────────────────────────────────────────
(async () => {
  console.log('Launching Chrome with your existing profile…');

  const browser = await chromium.launchPersistentContext(CONFIG.userDataDir, {
    headless:        false,
    channel:         'chrome',
    args:            ['--start-maximized'],
    viewport:        null,
  });

  const page = await browser.newPage();
  await page.goto('https://bumble.com/app', { waitUntil: 'domcontentloaded' });

  console.log('Waiting for Bumble to load…');
  // Wait until the swipe buttons are on screen
  await page.waitForSelector('.encounters-action--like', { timeout: 30_000 });

  console.log('Ready. Starting auto-swipe. Press Ctrl+C to stop.\n');

  let liked = 0, passed = 0;

  while (true) {
    try {
      // ── Dismiss any modal / match popup ──────────────────────────────────
      for (const sel of [
        '[data-qa-role="popup-dismiss"]',
        '[data-qa-role="match-action-button"]',
        '.modal__close-btn',
        '[aria-label="Close"]',
      ]) {
        const modal = page.locator(sel).first();
        if (await modal.isVisible().catch(() => false)) {
          await modal.click();
          await sleep(600);
        }
      }

      // ── Find swipe buttons ────────────────────────────────────────────────
      const likeBtn    = page.locator('.encounters-action--like').first();
      const dislikeBtn = page.locator('.encounters-action--dislike').first();

      const likeVisible    = await likeBtn.isVisible().catch(() => false);
      const dislikeVisible = await dislikeBtn.isVisible().catch(() => false);

      if (!likeVisible && !dislikeVisible) {
        process.stdout.write('\r[BAS] waiting for swipe buttons…');
        await sleep(2000);
        continue;
      }

      const wantLike = Math.random() < CONFIG.likeRatio;
      const btn      = wantLike
        ? (likeVisible    ? likeBtn    : dislikeBtn)
        : (dislikeVisible ? dislikeBtn : likeBtn);

      await btn.click();

      if (wantLike && likeVisible) liked++; else passed++;

      process.stdout.write(
        `\r[BAS] ${fmt(liked)} liked  ${fmt(passed)} passed   (running…)`
      );

      await sleep(rand(CONFIG.minDelay, CONFIG.maxDelay));

    } catch (err) {
      // Profile may have changed mid-action — just retry
      await sleep(1500);
    }
  }
})();
