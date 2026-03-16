"""
Bumble Smart Auto-Swipe — local VLM on Apple Silicon (M4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
First time:  bash setup.sh
Run:
  source /Users/qhungbui7/workspace/env/sandbox/bin/activate
  python smart_swipe.py           # normal mode
  python smart_swipe.py --debug   # debug mode (saves annotated images + full log)
"""

import argparse, json, time, random, re, os, io, subprocess, threading
from datetime import datetime
from pathlib import Path
import psutil
import ollama
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).parent
MODEL_DIR = ROOT / "models"
LOGS_DIR  = ROOT / "logs"
MODEL_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
os.environ["OLLAMA_MODELS"]     = str(MODEL_DIR)
os.environ["OLLAMA_KEEP_ALIVE"] = "60s"  # unload model after 60s idle → frees ~2 GB
os.environ["OLLAMA_METAL"]      = "1"    # force Metal GPU backend on Apple Silicon

# ── Config ────────────────────────────────────────────────────────────────────
CHROME_PROFILE = "/Users/qhungbui7/Library/Application Support/Google/Chrome/Default"

# qwen2.5vl:3b → 2.3 GB, SOTA accuracy, recommended  ← default
# qwen2.5vl:7b → 5.0 GB, most accurate, heavier
# moondream    → 1.8 GB, fastest but poor at body type judgment
VLM_MODEL   = "qwen2.5vl:3b"
VLM_MAX_PX  = 336   # smaller image = fewer tokens = less RAM (was 512)

# M4 Air safety limits
MAX_CPU_PCT = 90    # raised — M4 handles sustained load fine
MAX_MEM_PCT = 90    # raised — unified memory, 90% is normal under load
COOL_DOWN   = 5     # shorter pause — no need to wait 12s every swipe

# Swipe timing bands  (weight, min_sec, max_sec)
SWIPE_DELAYS = [
    (60, 1.5,  3.0),
    (25, 3.0,  6.0),
    (10, 6.0, 14.0),
    ( 4, 15., 35.0),
    ( 1, 45., 90.0),
]

# ── Preference prompt ─────────────────────────────────────────────────────────
# Edit the LIKE / PASS criteria freely.
AI_PROMPT = """You are evaluating a dating app profile photo.

Respond with exactly this format (one line):
  LIKE <confidence 0-100> | <short explanation>
  or
  PASS <confidence 0-100> | <short explanation>

LIKE if:
  - The person is NOT visibly overweight or obese
  - Bonus (raise confidence): nerdy/intellectual vibe — glasses, books, lab/study
    setting, anime merch, coding, science references, university look

PASS only if:
  - The person is visibly overweight or obese
  - No person visible in the photo at all

Examples:
  LIKE 92 | Slim build, glasses, bookshelf in background.
  LIKE 75 | Average build, nothing concerning.
  PASS 90 | Visibly overweight body type.
  PASS 80 | No person visible in photo.
""".strip()
# ─────────────────────────────────────────────────────────────────────────────


# ── Logging ───────────────────────────────────────────────────────────────────
class Logger:
    """
    Writes a JSONL session log and, in debug mode, saves annotated images.
    logs/
      session_YYYYMMDD_HHMMSS.jsonl   ← one JSON record per swipe
      debug/
        YYYYMMDD_HHMMSS_LIKE_90.jpg   ← annotated screenshot (debug only)
    """
    def __init__(self, debug: bool):
        self.debug    = debug
        ts            = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = LOGS_DIR / f"session_{ts}.jsonl"
        self.img_dir  = LOGS_DIR / "debug"
        if debug:
            self.img_dir.mkdir(exist_ok=True)
        print(f"  📄 Log → {self.log_file}")
        if debug:
            print(f"  🖼️  Debug images → {self.img_dir}")

    def record(self, decision: bool, confidence: int, explanation: str,
               profile_text: str, img_bytes: bytes | None):
        ts     = datetime.now().isoformat(timespec="seconds")
        label  = "LIKE" if decision else "PASS"
        record = {
            "ts":          ts,
            "decision":    label,
            "confidence":  confidence,
            "explanation": explanation,
            "profile":     profile_text,
        }
        with self.log_file.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        if self.debug and img_bytes:
            self._save_debug_image(img_bytes, label, confidence, explanation, ts)

    def _save_debug_image(self, img_bytes, label, confidence, explanation, ts):
        ts_safe = ts.replace(":", "").replace("-", "")
        fname   = f"{ts_safe}_{label}_{confidence}.jpg"
        img     = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        # Draw a coloured banner at the bottom
        banner_h = max(36, img.height // 8)
        full     = Image.new("RGB", (img.width, img.height + banner_h), (0, 0, 0))
        full.paste(img, (0, 0))
        draw     = ImageDraw.Draw(full)
        colour   = (60, 180, 60) if label == "LIKE" else (210, 50, 50)
        draw.rectangle([(0, img.height), (img.width, img.height + banner_h)], fill=colour)

        text = f"{label} {confidence}%  {explanation}"
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size=14)
        except Exception:
            font = ImageFont.load_default()
        draw.text((6, img.height + 6), text, fill=(255, 255, 255), font=font)

        (self.img_dir / fname).write_bytes(
            (lambda b: (b.seek(0), full.save(b, "JPEG", quality=85), b.getvalue())[2])(io.BytesIO())
        )


# ── Ollama helpers ────────────────────────────────────────────────────────────
def ensure_ollama():
    try:
        ollama.list(); return
    except Exception:
        pass
    print("  Starting Ollama…", end=" ", flush=True)
    env = {**os.environ, "OLLAMA_MODELS": str(MODEL_DIR)}
    subprocess.Popen(["ollama", "serve"], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(15):
        time.sleep(1)
        try:
            ollama.list(); print("OK"); return
        except Exception:
            pass
    print("FAILED — run 'ollama serve' manually")

def ensure_model():
    if not any(VLM_MODEL in m.model for m in ollama.list().models):
        print(f"  Pulling {VLM_MODEL}… (one-time download)")
        ollama.pull(VLM_MODEL)


# ── System health ─────────────────────────────────────────────────────────────
def check_health(label=""):
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory().percent
    if cpu > MAX_CPU_PCT or mem > MAX_MEM_PCT:
        print(f"\n  ⚠️  {label} CPU {cpu:.0f}% MEM {mem:.0f}% — cooling {COOL_DOWN}s",
              flush=True)
        time.sleep(COOL_DOWN)


# ── Timing ────────────────────────────────────────────────────────────────────
def human_delay():
    weights = [w for w, *_ in SWIPE_DELAYS]
    total, r, acc = sum(weights), random.uniform(0, sum(weights)), 0
    for w, lo, hi in SWIPE_DELAYS:
        acc += w
        if r <= acc:
            return random.uniform(lo, hi)
    return 2.0

def human_mouse_move(page, x, y):
    cur    = page.evaluate("()=>({x:window._mx||0,y:window._my||0})")
    cx, cy = cur.get("x", x), cur.get("y", y)
    steps  = random.randint(8, 16)
    cpx    = (cx+x)/2 + random.randint(-60, 60)
    cpy    = (cy+y)/2 + random.randint(-60, 60)
    for i in range(1, steps+1):
        t = i/steps
        page.mouse.move((1-t)**2*cx+2*(1-t)*t*cpx+t**2*x,
                        (1-t)**2*cy+2*(1-t)*t*cpy+t**2*y)
        time.sleep(random.uniform(0.008, 0.025))
    page.evaluate(f"()=>{{window._mx={x};window._my={y};}}")

def human_click(page, locator):
    box = locator.bounding_box()
    if not box:
        locator.click(); return
    cx = box["x"] + box["width"]/2  + random.uniform(-5, 5)
    cy = box["y"] + box["height"]/2 + random.uniform(-5, 5)
    human_mouse_move(page, cx, cy)
    time.sleep(random.uniform(0.08, 0.22))
    page.mouse.down(); time.sleep(random.uniform(0.05, 0.12)); page.mouse.up()

def card_tap(page, x, y):
    human_mouse_move(page, x, y)
    time.sleep(random.uniform(0.06, 0.15))
    page.mouse.down(); time.sleep(random.uniform(0.04, 0.09)); page.mouse.up()


# ── Card / profile helpers ────────────────────────────────────────────────────
def get_card_box(page):
    for sel in [".encounters-story", ".encounters-story-profile",
                ".encounters-story__content", ".card"]:
        el = page.locator(sel).first
        if el.is_visible():
            return el.bounding_box()
    return None

def scrape_profile_text(page) -> str:
    snippets = []
    for sel in [".encounters-story-profile__name", ".encounters-story-profile__age",
                ".encounters-story-profile__bio", ".encounters-story-profile__info",
                ".encounters-story__profile-name", ".profile-header"]:
        for el in page.locator(sel).all():
            try:
                t = el.inner_text().strip()
                if t: snippets.append(t)
            except Exception:
                pass
    return "\n".join(dict.fromkeys(snippets))

def screenshot_card(page) -> bytes | None:
    box = get_card_box(page)
    if not box:
        return None
    raw = page.screenshot(clip={"x": box["x"], "y": box["y"],
                                 "width": box["width"], "height": box["height"]})
    img = Image.open(io.BytesIO(raw))
    img.thumbnail((VLM_MAX_PX, VLM_MAX_PX), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    return buf.getvalue()


# ── AI evaluation ─────────────────────────────────────────────────────────────
_infer_lock = threading.Lock()

def ai_evaluate(page) -> tuple[bool, int, str, bytes | None]:
    """Returns (should_like, confidence, explanation, img_bytes)."""
    img_bytes    = screenshot_card(page)
    profile_text = scrape_profile_text(page)
    if not img_bytes:
        return random.random() < 0.85, 50, "no screenshot — fallback", None

    check_health("pre-inference")

    prompt = f"Profile text:\n{profile_text or '(none)'}\n\n{AI_PROMPT}"

    with _infer_lock:
        try:
            resp = ollama.chat(
                model=VLM_MODEL,
                messages=[{"role": "user", "content": prompt, "images": [img_bytes]}],
                options={
                    "num_predict": 40,   # enough for decision + explanation
                    "num_ctx":     256,  # tiny context window → small KV cache
                    "num_gpu":     999,  # offload ALL layers to Metal GPU (Apple Silicon)
                    "num_thread":  4,    # CPU threads for non-GPU work
                    "temperature": 0.0,
                },
            )
            raw = resp["message"]["content"].strip()
        except Exception as e:
            return random.random() < 0.85, 0, f"AI error: {e}", img_bytes

    check_health("post-inference")

    # parse  "LIKE 90 | explanation..."  or  "PASS 75 | explanation..."
    m = re.match(r"^(LIKE|PASS)\s+(\d+)\s*\|?\s*(.*)$", raw, re.IGNORECASE | re.DOTALL)
    if m:
        label, conf, expl = m.groups()
        return label.upper() == "LIKE", int(conf), expl.strip()[:120], img_bytes

    # fallback: just check first word
    like = raw.upper().startswith("LIKE")
    return like, 50, raw[:120], img_bytes


# ── Profile viewing ───────────────────────────────────────────────────────────
def view_profile(page):
    box = get_card_box(page)
    if not box:
        time.sleep(random.uniform(0.4, 1.0)); return
    x0, y0, w, h = box["x"], box["y"], box["width"], box["height"]

    action = random.choices(
        ["glance", "next_photos", "prev_then_next", "open_bio", "photos_then_bio"],
        weights=[25, 30, 10, 20, 15],
    )[0]

    if action == "glance":
        human_mouse_move(page, x0+w*random.uniform(0.2,0.8), y0+h*0.30)
        time.sleep(random.uniform(0.4, 1.2))

    elif action == "next_photos":
        for _ in range(random.randint(1, 3)):
            card_tap(page, x0+w*random.uniform(0.62,0.90), y0+h*random.uniform(0.10,0.55))
            time.sleep(random.uniform(0.7, 2.0))

    elif action == "prev_then_next":
        card_tap(page, x0+w*random.uniform(0.08,0.35), y0+h*random.uniform(0.10,0.55))
        time.sleep(random.uniform(0.5, 1.2))
        card_tap(page, x0+w*random.uniform(0.62,0.90), y0+h*random.uniform(0.10,0.55))
        time.sleep(random.uniform(0.5, 1.5))

    elif action == "open_bio":
        card_tap(page, x0+w*random.uniform(0.2,0.8), y0+h*random.uniform(0.62,0.85))
        time.sleep(random.uniform(0.6, 1.2))
        page.mouse.wheel(0, random.randint(150, 380))
        time.sleep(random.uniform(1.5, 4.0))
        if random.random() < 0.4:
            page.mouse.wheel(0, random.randint(80, 180))
            time.sleep(random.uniform(0.8, 2.0))
        card_tap(page, x0+w*random.uniform(0.2,0.8), y0+h*random.uniform(0.62,0.85))
        time.sleep(random.uniform(0.4, 0.8))

    elif action == "photos_then_bio":
        for _ in range(random.randint(1, 2)):
            card_tap(page, x0+w*random.uniform(0.62,0.90), y0+h*random.uniform(0.10,0.55))
            time.sleep(random.uniform(0.6, 1.6))
        card_tap(page, x0+w*random.uniform(0.2,0.8), y0+h*random.uniform(0.62,0.85))
        time.sleep(random.uniform(0.6, 1.0))
        page.mouse.wheel(0, random.randint(100, 300))
        time.sleep(random.uniform(1.2, 3.5))
        card_tap(page, x0+w*random.uniform(0.2,0.8), y0+h*random.uniform(0.62,0.85))
        time.sleep(random.uniform(0.3, 0.7))


# ── Session pacing ────────────────────────────────────────────────────────────
class SessionPacer:
    def __init__(self):
        self.count = 0
        self.next_break = random.randint(12, 25)
    def tick(self):
        self.count += 1
        if self.count >= self.next_break:
            pause = random.uniform(30, 120)
            print(f"\n  [break {pause:.0f}s…]", flush=True)
            time.sleep(pause)
            self.count = 0
            self.next_break = random.randint(12, 25)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true",
                        help="Save annotated screenshots to logs/debug/")
    args = parser.parse_args()

    print(f"🤖  Smart Swipe  model={VLM_MODEL}  debug={'ON' if args.debug else 'off'}\n")
    ensure_ollama()
    ensure_model()

    logger = Logger(debug=args.debug)
    liked = passed = 0

    def print_status(conf, expl):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        bar = "█" * (conf // 10) + "░" * (10 - conf // 10)
        print(f"\r  ✓{liked:>4} ✗{passed:>4}  [{bar}] {conf:>3}%  "
              f"CPU {cpu:>2.0f}% MEM {mem:>2.0f}%  {expl[:40]:<40}",
              end="", flush=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch_persistent_context(
                CHROME_PROFILE, channel="chrome",
                headless=False, no_viewport=True,
            )
        except Exception as e:
            print(f"\n❌  {e}\n👉  Close Chrome first.\n"); raise SystemExit(1)

        page = browser.new_page()
        page.evaluate("()=>{window._mx=0;window._my=0;}")
        page.goto("https://bumble.com/app")
        print("👉  Navigate to the swiping screen. Waiting up to 3 min…\n")
        page.wait_for_selector(".encounters-action--like", timeout=180_000)
        print("✅  Ready. Ctrl+C to stop.\n")

        pacer = SessionPacer()

        while True:
            try:
                for sel in ["[data-qa-role='popup-dismiss']",
                            "[data-qa-role='match-action-button']",
                            ".modal__close-btn", "[aria-label='Close']"]:
                    el = page.locator(sel).first
                    if el.is_visible():
                        time.sleep(random.uniform(0.3, 0.7))
                        human_click(page, el)
                        time.sleep(random.uniform(0.4, 0.8))

                like    = page.locator(".encounters-action--like").first
                dislike = page.locator(".encounters-action--dislike").first
                if not like.is_visible() and not dislike.is_visible():
                    time.sleep(2); continue

                should_like, conf, expl, img_bytes = ai_evaluate(page)
                profile_text = scrape_profile_text(page)

                view_profile(page)

                if should_like and like.is_visible():
                    human_click(page, like); liked += 1
                elif dislike.is_visible():
                    human_click(page, dislike); passed += 1
                else:
                    time.sleep(1); continue

                logger.record(should_like, conf, expl, profile_text, img_bytes)
                print_status(conf, expl)
                pacer.tick()
                time.sleep(human_delay())

            except KeyboardInterrupt:
                print(f"\n\nDone.  liked={liked}  passed={passed}  log={logger.log_file}")
                break
            except Exception:
                time.sleep(1.5)

if __name__ == "__main__":
    main()
