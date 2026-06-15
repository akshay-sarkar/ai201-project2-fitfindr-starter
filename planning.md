# FitFindr — planning.md

FitFindr is a thrift shopping agent that helps you find secondhand clothes and figure out how to actually wear them.

The basic idea: you describe what you're looking for, it searches a mock dataset of listings, picks the best match, and then uses an LLM to suggest outfits and write a little caption you could post somewhere. If anything goes wrong along the way (nothing found, wardrobe is empty, etc.) it tells you what happened instead of just breaking.

---

## Tools

### Tool 1: search_listings

**What it does:**
Looks through the listings dataset and returns anything that matches what the user asked for. Filters by size and price first, then scores each result based on how many keywords from the description show up in the listing's title, description, and style tags. Returns a ranked list — best match first. If nothing matches at all, returns an empty list (doesn't crash).

**Input parameters:**
- `description` (str): What the user is looking for, e.g. "vintage graphic tee". This gets split into keywords and matched against each listing.
- `size` (str | None): Size to filter by, e.g. "M". Uses substring matching so "M" will also match "S/M". Pass None to skip size filtering.
- `max_price` (float | None): Price ceiling, inclusive. Pass None to skip.

**What it returns:**
A list of listing dicts. Each one has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Sorted by relevance score, best first. Returns `[]` if nothing matches.

**What the agent does if it returns nothing:**
Checks immediately after the call. If the list is empty, sets an error message in the session like "No listings found for 'X' — try broader keywords or a higher price limit" and returns early. `suggest_outfit` and `create_fit_card` never get called with empty input.

---

### Tool 2: suggest_outfit

**What it does:**
Takes the item that was found and the user's wardrobe and asks the LLM to suggest 1-2 outfits. If the wardrobe is empty it still works — it just gives general styling advice instead of referencing specific pieces the user owns.

**Input parameters:**
- `new_item` (dict): The listing dict for the item being considered (comes from search_listings).
- `wardrobe` (dict): Has an `items` key with a list of wardrobe items. Each item has name, category, colors, style_tags, notes. Can be empty — handled.

**What it returns:**
A non-empty string with outfit ideas. If the wardrobe has items it'll name them specifically ("pair with your wide-leg khaki trousers"). If not, it gives general advice. Never returns an empty string.

**What happens if something goes wrong:**
- Empty wardrobe: switches to a different prompt that doesn't try to reference wardrobe pieces. Doesn't crash.
- LLM returns nothing: returns "Couldn't generate outfit suggestions right now. Try again shortly."

---

### Tool 3: create_fit_card

**What it does:**
Asks the LLM to write a short caption for the outfit — 2-4 sentences, first-person, casual. The kind of thing you'd actually caption an Instagram post with, not a product description. Runs at temperature 0.9 so it doesn't say the same thing every time.

**Input parameters:**
- `outfit` (str): The suggestion from suggest_outfit.
- `new_item` (dict): The listing dict — used to pull in the item name, price, and platform.

**What it returns:**
A short casual caption string. Mentions the item, price, and platform once each. Returns an error string (not an exception) if outfit is empty or blank.

**What happens if something goes wrong:**
- Empty outfit string: immediately returns "Couldn't create a fit card — outfit description was missing." No LLM call happens.
- LLM returns nothing: returns "Fit card generation failed. Try running the search again."

---

### Stretch Tool 4: compare_price

**What it does:**
Looks at how much the found item costs compared to other listings in the same category. No LLM involved — just averages the prices of comparable items and figures out if this one is cheap, average, or expensive. Returns a verdict and a human-readable message.

**Input parameters:**
- `item` (dict): The selected listing dict.

**What it returns:**
A dict with:
- `verdict`: "great deal", "fair price", or "on the high side"
- `item_price`, `avg_price`, `min_price`, `max_price`, `count`
- `message`: one sentence summary like "Y2K Baby Tee at $18 is right around the avg $22 for tops"

Thresholds: more than 20% below avg = great deal, more than 20% above = high side, everything in between = fair.

**If something goes wrong:**
Returns a dict with `verdict: "unknown"` and a reason. Never raises.

---

## Planning Loop

```
1. Parse the query
   - Pull out description, size (or None), max_price (or None) using regex
   - Store in session["parsed"]

2. Call search_listings(description, size, max_price)
   - Store results in session["search_results"]
   - If empty AND had size or price constraints:
       retry: search_listings(description, None, None)
       if retry worked:
           session["retry_attempted"] = True
           session["retry_message"] = what got loosened
           keep going
       if retry also empty:
           set session["error"]
           return early
   - If empty AND no constraints:
       set session["error"]
       return early
   - If not empty:
       session["selected_item"] = results[0]
       keep going

3. compare_price(selected_item) → session["price_comparison"]

4. Call suggest_outfit(selected_item, wardrobe)
   - Store in session["outfit_suggestion"]
   - (always returns something, so no early exit here)

5. Call create_fit_card(outfit_suggestion, selected_item)
   - Store in session["fit_card"]

6. Return session
```

The key thing: steps 3-5 only run if step 2 found something. The retry logic means the agent tries to recover before giving up rather than failing immediately on a tight query.

---

## State Management

Everything lives in the session dict that gets created at the start of `run_agent()`. Nothing gets passed back in by the user mid-session — each tool just reads from and writes to the session.

| Key | Type | Set when | Used by |
|-----|------|----------|---------|
| `query` | str | Start | Parsing |
| `parsed` | dict | After parsing | search_listings |
| `search_results` | list[dict] | After search | Branch check + selected_item |
| `selected_item` | dict | After branch | suggest_outfit, create_fit_card, compare_price |
| `wardrobe` | dict | Start (passed in) | suggest_outfit |
| `outfit_suggestion` | str | After suggest_outfit | create_fit_card |
| `fit_card` | str | After create_fit_card | Final output |
| `error` | str \| None | On early exit | UI error panel |
| `retry_attempted` | bool | After retry | UI retry notice |
| `retry_message` | str \| None | After retry | UI retry notice |
| `price_comparison` | dict \| None | After compare_price | UI price panel |

`selected_item` gets set once from `results[0]` and then gets passed into both `suggest_outfit` and `create_fit_card` as-is — no re-entry from the user.

---

## Error Handling

| Tool | What can fail | What happens |
|------|--------------|--------------|
| `search_listings` | Nothing matches the query | Returns `[]`, agent sets error message and exits early. suggest_outfit and create_fit_card never run. |
| `search_listings` (retry) | First search empty with constraints | Agent retries without size/price. If retry works, sets retry_message and continues. If retry also fails, sets error and exits. |
| `suggest_outfit` | Wardrobe is empty | Uses a different LLM prompt that gives general advice instead of referencing wardrobe pieces. Never crashes. |
| `create_fit_card` | outfit string is empty | Returns an error string immediately, doesn't call the LLM at all. |
| `compare_price` | No category, or no comparables | Returns `verdict: "unknown"` with a reason. Never crashes. |

---

## Architecture

```
User query
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                        run_agent()                          │
│                                                             │
│  Step 1: parse query                                        │
│          → session["parsed"]                               │
│                    │                                        │
│                    ▼                                        │
│  Step 2: search_listings(description, size, max_price)      │
│                    │                                        │
│          ┌─────────┴──────────┐                            │
│       empty               not empty                        │
│          │                    │                            │
│     constraints?              ▼                            │
│     yes → retry         session["selected_item"]           │
│       found → continue        │                            │
│       still empty → error     ▼                            │
│     no → error          Step 3: compare_price(             │
│          │                selected_item)                   │
│       RETURN                  │                            │
│       early                   ▼                            │
│                        Step 4: suggest_outfit(             │
│                          selected_item, wardrobe)          │
│                               │                            │
│                       wardrobe empty?                      │
│                       yes → general advice                 │
│                       no  → use wardrobe pieces            │
│                               │                            │
│                               ▼                            │
│                        Step 5: create_fit_card(            │
│                          outfit_suggestion, selected_item) │
│                               │                            │
│                               ▼                            │
│                         return session                     │
└─────────────────────────────────────────────────────────────┘
      │
      ▼
handle_query() in app.py
  → listing panel, outfit panel, fit card panel, price panel
  → retry notice if constraints were loosened
  → error panel if something failed
```

---

## AI Tool Plan

### Milestone 3 — tools

**search_listings:**
I gave Claude the Tool 1 spec from this file — inputs, return shape, failure mode — and asked it to implement the function using `load_listings()`. Before running it I checked that it was doing substring matching for size (not equality) and that items scoring 0 were actually excluded. Tested with 3 queries: graphic tee with no filters, impossible ballgown query, jacket with $10 price cap.

**suggest_outfit:**
Gave Claude the Tool 2 spec plus the wardrobe schema. Checked that it actually branched on empty wardrobe before the LLM call (not after). Ran it twice — once with the example wardrobe to confirm it named pieces, once with the empty wardrobe to confirm no crash and general advice.

**create_fit_card:**
Gave Claude the Tool 3 spec with the style guidelines and the temperature requirement. Before running I checked that the empty outfit guard was before the Groq call, not after. Ran it 3 times on the same input to confirm the output varied (would've been a problem if temperature wasn't actually 0.9).

### Milestone 4 — planning loop

Gave Claude the architecture diagram above and the planning loop + state management sections. When I got the code I checked: does the no-results branch set fit_card to None (not empty string)? Does selected_item come from results[0] before passing into suggest_outfit? Do the session keys match what's in _new_session()? All looked good. Ran python agent.py to verify state was actually flowing between steps.

### Stretch features

For each one I gave Claude the spec section from this file plus the existing code as context. Told it where each should slot into agent.py (retry inside step 2, compare_price at step 3). After getting the code I checked: compare_price filters out the item itself using `!=` not `==`; retry only fires when constraints were actually present; error message names exactly what was loosened. Then ran python agent.py across all 3 test paths before touching app.py.

---

## A Complete Interaction

**Example query:** "looking for a vintage graphic tee under $30"

**Step 1 — Parse the query:**
The agent pulls out `description = "vintage graphic tee"`, `size = None`, `max_price = 30.0` using regex. This has to happen first because search_listings needs structured parameters — it can't take a raw sentence.

**Step 2 — Call search_listings:**
search_listings is called first because nothing else can run without a result. It uses the parsed description and $30 ceiling, scores every listing by keyword overlap, and returns Y2K Baby Tee ($18) as the top match. selected_item is set to that dict. The agent checks immediately — if the list were empty it would stop here and tell the user what to try instead.

**Step 3 — Call compare_price:**
Now that there's a selected item, compare_price runs to check if $18 is actually a good deal. It looks at all other tops in the dataset, finds the average is around $22, and returns "fair price" since $18 is within 20% of that. This runs before outfit suggestions because it only depends on the item — it doesn't need the wardrobe.

**Step 4 — Call suggest_outfit:**
suggest_outfit runs next because it needs the selected item (from step 2) to know what piece to style. It also needs the wardrobe. Since the wardrobe has items, the LLM prompt includes all of them by name and returns combinations referencing Baggy straight-leg jeans, Chunky white sneakers, and Black combat boots specifically. The result is stored in the session so create_fit_card can use it without the user re-entering anything.

**Step 5 — Call create_fit_card:**
create_fit_card runs last because it depends on the outfit suggestion from step 4. It can't run before suggest_outfit — it needs something to write a caption about. The LLM takes the outfit text and the item details and produces a short casual caption mentioning the Y2K Baby Tee, $18, and depop. temperature=0.9 means it'll phrase it differently each time.

**Final output:** listing panel, outfit panel, fit card panel, price check panel (🟡 fair price).

**What would have happened with a tight query:**
"vintage tee size XXS under $5" — search returns nothing because no XXS tees exist under $5. The agent doesn't stop there; it tries again without the size and price filters because those were the constraints. The retry finds Y2K Baby Tee and the rest of the pipeline runs normally. The UI shows a notice explaining what was loosened.

**What would have happened with an impossible query:**
"designer ballgown size XXS under $5" — first search empty, retry also empty because "ballgown" doesn't match anything in the dataset at any price. The agent sets an error message and returns. suggest_outfit and create_fit_card never run.
