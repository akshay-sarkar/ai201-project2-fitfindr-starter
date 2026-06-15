"""
tools.py — all FitFindr tools

Required:
    search_listings(description, size, max_price)   → list[dict]
    suggest_outfit(new_item, wardrobe)               → str
    create_fit_card(outfit, new_item)                → str

Stretch:
    compare_price(item)                              → dict
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── groq helpers ──────────────────────────────────────────────────────────────

def _get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set. Add it to a .env file.")
    return Groq(api_key=api_key)


def _call_groq(prompt: str, temperature: float = 0.7) -> str:
    """Call Groq and return the response text. Returns '' on failure."""
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1024,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Groq error] {e}")
        return ""


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search listings by keyword relevance.

    Filters by size (case-insensitive substring) and price first,
    then scores remaining items by how many description keywords appear
    in title + description + style_tags + category.

    Returns a list sorted best-first. Returns [] if nothing matches — no exception.
    """
    all_listings = load_listings()

    # hard filters first — cheaper than scoring everything
    candidates = []
    for item in all_listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and size.lower() not in item["size"].lower():
            continue
        candidates.append(item)

    # score by keyword overlap
    keywords = re.findall(r"\w+", description.lower())

    scored = []
    for item in candidates:
        blob = " ".join([
            item["title"].lower(),
            item["description"].lower(),
            " ".join(item["style_tags"]).lower(),
            item["category"].lower(),
        ])
        score = sum(1 for kw in keywords if kw in blob)
        if score > 0:
            scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Suggest 1-2 outfits for the given item.

    If the wardrobe has items, the LLM references them by name.
    If empty, falls back to general styling advice.

    Always returns a non-empty string.
    """
    item_summary = (
        f"Item: {new_item['title']}\n"
        f"Category: {new_item['category']}\n"
        f"Colors: {', '.join(new_item['colors'])}\n"
        f"Style tags: {', '.join(new_item['style_tags'])}\n"
        f"Condition: {new_item['condition']}\n"
        f"Price: ${new_item['price']:.2f}\n"
        f"Platform: {new_item['platform']}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        # no wardrobe — give general advice instead
        prompt = (
            "You are a personal stylist specialising in thrift and secondhand fashion.\n\n"
            "A user is considering buying this thrifted item:\n"
            f"{item_summary}\n\n"
            "They haven't told you what's in their wardrobe yet. "
            "Give them 1-2 short, specific outfit ideas — describe the vibe, "
            "what kinds of pieces pair well, and one styling tip. "
            "Be direct and conversational — no bullet points, just natural suggestions."
        )
    else:
        # build a wardrobe summary to pass into the prompt
        wardrobe_lines = []
        for w in wardrobe_items:
            notes = f" ({w['notes']})" if w.get("notes") else ""
            wardrobe_lines.append(
                f"- {w['name']} [{w['category']}] — "
                f"colors: {', '.join(w['colors'])}; "
                f"tags: {', '.join(w['style_tags'])}{notes}"
            )

        prompt = (
            "You are a personal stylist specialising in thrift and secondhand fashion.\n\n"
            "A user is considering buying this thrifted item:\n"
            f"{item_summary}\n\n"
            "Their current wardrobe:\n"
            f"{chr(10).join(wardrobe_lines)}\n\n"
            "Suggest 1-2 complete outfit combinations using the new item and specific "
            "pieces from their wardrobe — reference them by name. "
            "Describe the vibe and add one concrete styling tip. "
            "Be direct and conversational — no bullet points."
        )

    result = _call_groq(prompt, temperature=0.7)
    if not result:
        return "Couldn't generate outfit suggestions right now. Try again shortly."
    return result


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Write a short Instagram-style caption for the outfit.

    Casual first-person voice — should sound like a real person, not ad copy.
    Mentions item name, price, and platform once each.
    Runs at temperature 0.9 so output varies across calls.

    Returns an error string (not an exception) if outfit is empty.
    """
    if not outfit or not outfit.strip():
        return "Couldn't create a fit card — outfit description was missing."

    title    = new_item.get("title", "thrifted piece")
    price    = new_item.get("price", 0)
    platform = new_item.get("platform", "a thrift platform")

    prompt = (
        "You are writing an Instagram caption for a thrift outfit post.\n\n"
        f"The thrifted item: {title} — ${price:.2f} from {platform}\n\n"
        f"The outfit: {outfit}\n\n"
        "Write a 2-4 sentence caption in a casual, authentic first-person voice.\n"
        "Rules:\n"
        "- Sound like a real person posting an OOTD, not a brand\n"
        "- Mention the item name once, the price once, the platform once\n"
        "- Capture the outfit vibe in specific terms\n"
        "- No hashtags, no quotation marks, don't start with 'I'\n"
        "Output only the caption text."
    )

    result = _call_groq(prompt, temperature=0.9)
    if not result:
        return "Fit card generation failed. Try running the search again."
    return result


# ── Stretch Tool 4: compare_price ─────────────────────────────────────────────

def compare_price(item: dict) -> dict:
    """
    Compare the item's price against other listings in the same category.

    Verdict thresholds:
        >20% below avg → "great deal"
        >20% above avg → "on the high side"
        within 20%     → "fair price"

    Returns a dict with verdict, avg_price, min_price, max_price, count, message.
    Returns verdict="unknown" with a reason if something goes wrong — never raises.
    """
    try:
        category   = item.get("category", "")
        item_price = float(item.get("price", 0))
        item_title = item.get("title", "this item")

        if not category:
            return _price_error("Item has no category to compare against.")

        all_listings = load_listings()
        comparables = [
            l for l in all_listings
            if l.get("category") == category and l.get("id") != item.get("id")
        ]

        if not comparables:
            return _price_error(f"No other {category} listings to compare against.")

        prices    = [float(l["price"]) for l in comparables]
        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        pct_diff  = (item_price - avg_price) / avg_price

        if pct_diff <= -0.20:
            verdict = "great deal"
            message = (
                f"{item_title} at ${item_price:.2f} is "
                f"{abs(pct_diff)*100:.0f}% below the avg ${avg_price:.2f} "
                f"for {category} — solid find."
            )
        elif pct_diff >= 0.20:
            verdict = "on the high side"
            message = (
                f"{item_title} at ${item_price:.2f} is "
                f"{pct_diff*100:.0f}% above the avg ${avg_price:.2f} "
                f"for {category} — worth negotiating if you can."
            )
        else:
            verdict = "fair price"
            message = (
                f"{item_title} at ${item_price:.2f} is right around the avg "
                f"${avg_price:.2f} for {category} — reasonably priced."
            )

        return {
            "verdict":    verdict,
            "item_price": item_price,
            "avg_price":  round(avg_price, 2),
            "min_price":  min_price,
            "max_price":  max_price,
            "count":      len(comparables),
            "message":    message,
        }

    except Exception as e:
        return _price_error(f"Price comparison failed: {e}")


def _price_error(reason: str) -> dict:
    return {
        "verdict":    "unknown",
        "item_price": 0.0,
        "avg_price":  0.0,
        "min_price":  0.0,
        "max_price":  0.0,
        "count":      0,
        "message":    reason,
    }
