# bumble-autoswipe

Automated Bumble swiping on macOS with optional local AI filtering.  
Uses Playwright for real trusted browser input and Ollama for on-device vision inference.

---

## Project layout

```
swipe/
├── setup.sh          # one-time setup (installs deps + pulls VLM model)
├── swipe.py          # basic auto-swipe with human-behaviour simulation
├── smart_swipe.py    # AI-powered swipe — filters by photo using local VLM
├── models/           # Ollama model weights (~2.3 GB for qwen2.5vl:3b)
└── logs/
    ├── session_YYYYMMDD_HHMMSS.jsonl   # one record per swipe
    └── debug/
        └── YYYYMMDD_HHMMSS_LIKE_90.jpg # annotated screenshots (--debug only)
```

---

## Requirements

| Requirement | Notes |
|---|---|
| macOS (Apple Silicon) | Tested on M4 Air; M1/M2/M3 also fine |
| Python 3.11+ | `brew install python` |
| Google Chrome | Must be installed, not just Chromium |
| Homebrew | For installing Ollama |

---

## Setup (one time)

```bash
bash setup.sh
```

This will:
1. `pip install` all Python dependencies
2. Install **Ollama** via Homebrew if not already present
3. Pull the **moondream** vision model (~1.8 GB) into `./models/`
4. Create the `./cache/screens/` directory

---

## Usage

### Basic auto-swipe (`swipe.py`)

No AI — swipes based on a configurable like ratio with human-behaviour simulation.

```bash
python swipe.py
```

**Config** (top of file):

| Variable | Default | Description |
|---|---|---|
| `LIKE_RATIO` | `0.85` | Fraction of profiles to like |
| `CHROME_PROFILE` | `~/Library/.../Chrome/Default` | Path to your Chrome profile |

---

### Smart auto-swipe (`smart_swipe.py`)

Evaluates each profile photo with a local VLM before swiping.

```bash
python smart_swipe.py           # normal mode
python smart_swipe.py --debug   # saves annotated screenshots to logs/debug/
```

**Config** (top of file):

| Variable | Default | Description |
|---|---|---|
| `VLM_MODEL` | `moondream` | Ollama model to use (see [Model options](#model-options)) |
| `AI_PROMPT` | see file | Criteria sent to the VLM — edit to match your preferences |
| `MAX_CPU_PCT` | `80` | Pause inference if CPU exceeds this |
| `MAX_MEM_PCT` | `82` | Pause inference if RAM exceeds this |
| `VLM_MAX_PX` | `512` | Resize image to this before sending — smaller = faster |
| `CHROME_PROFILE` | `~/Library/.../Chrome/Default` | Path to your Chrome profile |

The console shows a live status line:
```
  ✓  47 like  ✗  12 pass  CPU  34%  MEM  61%  Appears to be a slim woman.
```

Screenshots of every evaluated profile are saved to `cache/screens/` as timestamped JPEGs so you can audit the AI's decisions.

---

## Model options

All models are **open-source** and run fully offline after the initial download.

| Model | Size | Speed (M4) | Notes |
|---|---|---|---|
| `qwen2.5vl:3b` | 2.3 GB | ~2–3 s/image | **default** — best balance, strong gender/body understanding |
| `qwen2.5vl:7b` | 5.0 GB | ~5–8 s/image | more accurate, needs more RAM |
| `moondream` | 1.8 GB | ~1–2 s/image | fastest, weaker on body/gender |

To switch models, change `VLM_MODEL` in `smart_swipe.py` and pull it first:

```bash
OLLAMA_MODELS=./models ollama pull qwen2.5vl:7b
```

---

## How it works

### Human-behaviour simulation

Each swipe cycle:
1. **AI evaluates** the current profile photo (smart mode only)
2. **Profile viewing** is simulated — one of five behaviours chosen randomly:
   - quick glance (mouse drift over photo)
   - browse photos (tap top-right of card 1–3×)
   - accidental back-then-forward (tap top-left then top-right)
   - open bio (tap bottom half → scroll → close)
   - browse photos then open bio
3. **Swipe delay** is drawn from a weighted distribution with rare outliers
   that mimic distraction, reading, or putting the phone down
4. Every 12–25 swipes a **session break** of 30–120 s is taken

### Delay distribution

| Band | Weight | Range | Simulates |
|---|---|---|---|
| Fast swipe | 60% | 1.5–3 s | quick decision |
| Pause | 25% | 3–6 s | second look |
| Reading | 10% | 6–14 s | reading bio |
| Distracted | 4% | 15–35 s | phone down briefly |
| Coffee | 1% | 45–90 s | long break |

### M4 safety limits

- CPU and RAM are checked **before and after** every VLM inference
- If either exceeds the configured limit the script sleeps for `COOL_DOWN` seconds
- Only one inference runs at a time (mutex lock)
- Images are resized to 512 px max before inference — halves memory use
- Model output is capped at 3 tokens (`num_predict: 3`) — single-word answer

---

## Troubleshooting

**`Could not open Chrome profile`**  
Close Chrome completely (`Cmd+Q`) before running the script.

**`wait_for_selector` timeout**  
The script waits 3 minutes for the swiping screen to appear — just log in and
navigate to the encounters screen manually after Chrome opens.

**Ollama not starting**  
Run `OLLAMA_MODELS=./models ollama serve` in a separate terminal, then retry.

**Wrong model stored outside project folder**  
Make sure you always run with `OLLAMA_MODELS=./models` set, or use the provided
scripts which set this automatically.
