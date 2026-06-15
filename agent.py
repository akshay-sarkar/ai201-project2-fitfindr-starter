"""
agent.py — FitFindr planning loop

Runs a query through all the tools in sequence, passing state via a session dict.
The main decision point is after search — if nothing was found, the agent tries
to recover before giving up.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    session = run_agent("vintage graphic tee under $30", get_example_wardrobe())
    print(session["fit_card"])
    print(session["error"])  # None if everything worked
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card, compare_price


# ── session ───────────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    return {
        "query":             query,
        "parsed":            {},
        "search_results":    [],
        "selected_item":     None,
        "wardrobe":          wardrobe,
        "outfit_suggestion": None,
        "fit_card":          None,
        "error":             None,
        # stretch
        "retry_attempted":   False,
        "retry_message":     None,
        "price_comparison":  None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Pull description, size, and max_price out of a natural language query.

    Uses regex — not perfect, but handles most common patterns like
    "under $30", "size M", "vintage tee size S/M under $40".

    Returns all three keys always; size and max_price are None if not found.
    """
    # price: matches "under $30", "$40", "up to $25", etc.
    price_match = re.search(
        r"(?:under|up\s+to|max|below)?\s*\$?(\d+(?:\.\d+)?)",
        query, re.IGNORECASE,
    )
    max_price = float(price_match.group(1)) if price_match else None

    # size: "size M", "size S/M", or bare size tokens
    size_match = re.search(
        r"\bsize\s+([A-Z0-9/]+)\b"
        r"|\b(XXS|XS|S/M|M/L|L/XL|XL/XXL|SM|ML|S|M|L|XL|XXL)\b",
        query, re.IGNORECASE,
    )
    size = None
    if size_match:
        size = (size_match.group(1) or size_match.group(2)).upper()

    # description: everything left after removing price and size fragments
    description = query
    description = re.sub(
        r"(?:under|up\s+to|max|below)\s*\$?\d+(?:\.\d+)?",
        "", description, flags=re.IGNORECASE,
    )
    description = re.sub(r"\$\d+(?:\.\d+)?", "", description)
    description = re.sub(
        r"\b(?:in\s+)?size\s+[A-Z0-9/]+\b"
        r"|\b(?:XXS|XS|S/M|M/L|L/XL|XL/XXL|SM|ML|S|M|L|XL|XXL)\b",
        "", description, flags=re.IGNORECASE,
    )
    description = re.sub(r"[,\-]+", " ", description)
    description = re.sub(r"\s{2,}", " ", description).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main entry point. Runs the query through all tools and returns the session.

    Always check session["error"] first — if it's set, the run ended early
    and outfit_suggestion / fit_card will be None.
    """

    # init
    session = _new_session(query, wardrobe)

    # parse
    session["parsed"] = _parse_query(query)
    description = session["parsed"]["description"]
    size        = session["parsed"]["size"]
    max_price   = session["parsed"]["max_price"]

    # search
    session["search_results"] = search_listings(description, size, max_price)

    # retry with loosened constraints if we got nothing
    if not session["search_results"]:
        loosened = []
        if size is not None:
            loosened.append(f"size filter (was: {size})")
        if max_price is not None:
            loosened.append(f"price limit (was: ${max_price:.0f})")

        if loosened:
            retry_results = search_listings(description, None, None)
            if retry_results:
                session["search_results"]  = retry_results
                session["retry_attempted"] = True
                session["retry_message"]   = (
                    f"No exact matches found — automatically loosened "
                    f"{' and '.join(loosened)} to find you something close."
                )

    # if still nothing, give up
    if not session["search_results"]:
        parts = [f"'{description}'"]
        if size:
            parts.append(f"size: {size}")
        if max_price is not None:
            parts.append(f"max: ${max_price:.0f}")
        context = " (" + ", ".join(parts[1:]) + ")" if len(parts) > 1 else ""
        session["error"] = (
            f"No listings found for {parts[0]}{context} even after loosening constraints. "
            f"Try different keywords or a broader search."
        )
        return session

    # pick the top result
    session["selected_item"] = session["search_results"][0]

    # price comparison
    session["price_comparison"] = compare_price(session["selected_item"])

    # outfit suggestion
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
    )

    # fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    return session


# ── quick CLI test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Parsed:      {session['parsed']}")
        print(f"Found:       {session['selected_item']['title']} — ${session['selected_item']['price']}")
        print(f"Price check: {session['price_comparison']['message']}")
        if session["retry_message"]:
            print(f"Retry:       {session['retry_message']}")
        print(f"\nOutfit suggestion:\n{session['outfit_suggestion']}")
        print(f"\nFit card:\n{session['fit_card']}")

    print("\n\n=== Retry path: tight constraints ===\n")
    session2 = run_agent(
        query="vintage graphic tee size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    if session2["error"]:
        print(f"Error: {session2['error']}")
    else:
        print(f"Retry attempted: {session2['retry_attempted']}")
        print(f"Retry message:   {session2['retry_message']}")
        print(f"Found after retry: {session2['selected_item']['title']}")

    print("\n\n=== No-results path: impossible query ===\n")
    session3 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error:             {session3['error']}")
    print(f"fit_card:          {session3['fit_card']}")
    print(f"outfit_suggestion: {session3['outfit_suggestion']}")
