# FitFindr

A multi-tool AI agent for thrift shopping. You describe what you're looking for, it searches a mock listings dataset, picks the best match, checks if the price is fair, suggests outfits based on your wardrobe, and writes a caption for it.

Built for AI201 Week 2.

---

## Setup

```bash
# clone your fork and enter the directory
git clone <your-fork-url>
cd ai201-project2-fitfindr-starter

# create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # mac/linux
source .venv/Scripts/activate    # windows git bash

# install dependencies
pip install -r requirements.txt

# add your Groq key to a .env file
# free key at console.groq.com, no credit card needed
echo "GROQ_API_KEY=your_key_here" > .env

# run the app
python app.py
# open the URL it prints (usually localhost:7860)
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

Searches the mock dataset. No LLM involved — pure Python filtering and keyword scoring.

| Parameter | Type | What it does |
|-----------|------|---------|
| `description` | `str` | What you're looking for, e.g. `"vintage graphic tee"` |
| `size` | `str \| None` | Size filter. Case-insensitive substring — `"M"` matches `"S/M"`. Pass `None` to skip. |
| `max_price` | `float \| None` | Price ceiling, inclusive. Pass `None` to skip. |

Returns a list of matching listing dicts, best match first. Each listing has 11 fields: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` if nothing matches — never raises.

Scoring: counts how many description keywords appear in each listing's title + description + style_tags + category. Anything scoring 0 gets dropped.

---

### `suggest_outfit(new_item, wardrobe)`

Calls the Groq LLM to suggest 1-2 outfit ideas for the found item. If the wardrobe has items, it references them by name. If not, it gives general styling advice. Always returns something.

| Parameter | Type | What it does |
|-----------|------|---------|
| `new_item` | `dict` | The listing dict for the item (output of search_listings) |
| `wardrobe` | `dict` | Has an `items` key. Can be empty — handled. |

Returns a non-empty string with outfit suggestions. Never crashes on empty wardrobe.

---

### `create_fit_card(outfit, new_item)`

Writes a short Instagram-style caption for the outfit. Casual first-person voice, not a product description. Runs at temperature 0.9 so the output varies each time.

| Parameter | Type | What it does |
|-----------|------|---------|
| `outfit` | `str` | The outfit suggestion string from suggest_outfit |
| `new_item` | `dict` | Used to pull in item name, price, and platform for the caption |

Returns a 2-4 sentence caption mentioning the item name, price, and platform. If `outfit` is empty or blank, returns an error string — no LLM call, no exception.

---

### `compare_price(item)` — stretch

Compares the item's price to other listings in the same category. No LLM, just averaging.

| Parameter | Type | What it does |
|-----------|------|---------|
| `item` | `dict` | The selected listing |

Returns a dict: `verdict` (great deal / fair price / on the high side), `avg_price`, `min_price`, `max_price`, `count`, `message`. Returns `verdict: "unknown"` if something goes wrong — never raises.

---

## How the Planning Loop Works

The agent doesn't call all tools in a fixed sequence. The main decision point is after search — if nothing was found, it tries to recover before giving up.

```
1. Init session

2. Parse query → description, size, max_price

3. search_listings(description, size, max_price)
   → session["search_results"]

   if empty AND had size or price constraints:
     retry without those constraints
     if retry worked → set retry_message, continue
     if still empty → set error, return early

   if empty AND no constraints → set error, return early

4. selected_item = results[0]

5. compare_price(selected_item) → session["price_comparison"]

6. suggest_outfit(selected_item, wardrobe)
   → session["outfit_suggestion"]

7. create_fit_card(outfit_suggestion, selected_item)
   → session["fit_card"]

8. return session
```

Steps 4-7 only run if there's a result. The retry at step 3 is the agent making an actual decision — loosening constraints rather than failing immediately.

**Why this order:** search runs first because every other tool depends on having an item. compare_price only needs the item so it runs right after selection. suggest_outfit needs both the item and the wardrobe, so it runs before create_fit_card which in turn needs the outfit text. None of these steps could run in a different order without breaking the data dependencies.

---

## State Management

Everything is stored in one session dict that gets created at the start of `run_agent()`. No data gets passed back in by the user between steps.

| Key | Type | Set when | Used by |
|-----|------|----------|-------------|
| `query` | `str` | Start | Parsing |
| `parsed` | `dict` | After parsing | search_listings |
| `search_results` | `list[dict]` | After search | Branch check |
| `selected_item` | `dict` | After branch | suggest_outfit, create_fit_card, compare_price |
| `wardrobe` | `dict` | Start | suggest_outfit |
| `outfit_suggestion` | `str` | After suggest_outfit | create_fit_card |
| `fit_card` | `str` | After create_fit_card | Output |
| `error` | `str \| None` | On early exit | UI error panel |
| `retry_attempted` | `bool` | After retry | UI notice |
| `retry_message` | `str \| None` | After retry | UI notice |
| `price_comparison` | `dict \| None` | After compare_price | Price panel |

`selected_item` gets set once from `results[0]` and flows directly into both `suggest_outfit` and `create_fit_card` — same dict, no re-entry from the user. `outfit_suggestion` is set once by suggest_outfit and passed directly into create_fit_card the same way.

---

## Error Handling

All three required tools have explicit failure modes. Here's what the agent does in each case:

### search_listings — returns nothing

search_listings is the only tool that can cause an early exit. The agent first attempts a retry with size and price constraints removed. If that also returns nothing, it sets a specific error message and exits — `suggest_outfit` and `create_fit_card` never run with empty input.

```
Query: "designer ballgown size XXS under $5"
→ first search: []
→ retry without constraints: still []
→ error: "No listings found for 'designer ballgown' (size: XXS, max: $5)
          even after loosening constraints. Try different keywords."
fit_card: None  |  outfit_suggestion: None
```

---

### suggest_outfit — wardrobe is empty

When `wardrobe["items"]` is empty, suggest_outfit doesn't crash or return nothing — it switches to a general styling prompt that gives advice without trying to reference pieces the user hasn't told us about.

```
Input: Y2K Baby Tee, empty wardrobe
Output: "For a cottagecore-inspired look, pair with a flowy high-waisted skirt..."
(no named wardrobe pieces — confirms the correct branch was taken)
```

---

### create_fit_card — outfit string is empty

create_fit_card checks for an empty outfit string before making any LLM call. If the string is empty or whitespace-only, it returns a descriptive error message immediately — no API call, no exception.

```
Input: outfit=""
Output: "Couldn't create a fit card — outfit description was missing."
```

---

### retry kicked in — constraints were loosened

This isn't a failure — it's the agent recovering from one. When the first search fails but the query had size or price constraints, the agent retries automatically and tells the user exactly what changed.

```
Query: "vintage tee size XXS under $5"
→ first search: []
→ retry: loosened size filter (was: XXS) and price limit (was: $5)
→ found: Y2K Baby Tee — Butterfly Print
→ UI shows: "No exact matches found — automatically loosened size filter
             (was: XXS) and price limit (was: $5) to find you something close."
```

---

## Stretch Features

### Price comparison (+2)

`compare_price()` in tools.py. Runs after a listing is selected, before outfit suggestions.

**How comparisons are made:** loads all listings, filters to the same `category` as the selected item (e.g. all "tops"), excludes the item itself, then computes the average price of what's left. The item's price is compared against that average using a ±20% threshold — more than 20% below average is "great deal", more than 20% above is "on the high side", within 20% is "fair price". The result also includes category min, max, and comparable count. No LLM involved.

Example from testing: Y2K Baby Tee at $18.00, category avg for tops is $22.00. $18 is 18% below average, within the threshold → verdict "fair price". Shown in the 💰 Price check panel.

---

### Retry logic with fallback (+1)

In `run_agent()`, between the first search call and the error exit. If search returns empty and the query had a size or price constraint, the agent retries with both removed and tells the user exactly what was loosened.

Example from testing: "vintage tee size XXS under $5" → first search empty → retry without size/price → found Y2K Baby Tee → UI shows "No exact matches found — automatically loosened size filter (was: XXS) and price limit (was: $5) to find you something close."

---

## Tests

```bash
pytest tests/ -v
```

23 tests, all passing. Covers the three required tools and their failure modes — empty results, empty wardrobe, empty outfit string, size filtering, price filtering, relevance sorting, output variation.

---

## Spec Reflection

**What helped:** Writing out the planning loop step by step before touching agent.py made implementation a lot more straightforward. The branch condition was already decided — when search returns nothing, set the error and exit, don't call the other tools. Without that written down first it would've been easy to accidentally write code that calls suggest_outfit with an empty list and gets a weird LLM response.

**Where it diverged:** The spec assumed the description would come out clean after stripping size and price tokens. In practice the regex leaves filler like "looking for a" in the description string. Turned out not to matter because those words don't score against any listing, but the spec was optimistic about how clean the parser output would be.

---

## AI Usage

**Instance 1 — implementing the three tools**

I gave Claude the spec for each tool one at a time — inputs, return shape, failure mode — and asked it to implement it in tools.py using load_listings() from the data loader. For each one I checked the key decisions before running: size filter uses substring match not equality, search drops zero-score items, create_fit_card guards empty input before calling the LLM. Then ran the tests to confirm.

**Instance 2 — planning loop in agent.py**

Gave Claude the architecture diagram from planning.md and the planning loop + state management sections, asked for run_agent() and _parse_query(). Before running I checked: no-results branch sets fit_card to None not empty string, selected_item comes from results[0] and flows directly into suggest_outfit without going through the user again, session keys match what's in _new_session(). Ran python agent.py to verify state was actually passing between steps.

**Instance 3 — stretch features**

For the two stretch features I gave Claude the spec section plus the existing code. Called out exactly where each thing should slot into agent.py (retry between steps 3 and 4, compare_price at step 5). After getting the code I checked: compare_price excludes the item itself using !=, retry only fires when constraints were actually present, error message names exactly what was loosened. Ran python agent.py across all three test cases before updating app.py.

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # wardrobe format + 10-item example wardrobe
├── tests/
│   └── test_tools.py          # 23 tests
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── agent.py                   # planning loop
├── app.py                     # gradio UI, 4 output panels
├── tools.py                   # 4 tools: search_listings, suggest_outfit, create_fit_card, compare_price
├── planning.md                # spec written before implementation
├── requirements.txt
└── .env                       # api key, not committed
```
