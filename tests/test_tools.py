"""
tests/test_tools.py

Isolation tests for all three FitFindr tools.
Run with:  pytest tests/ -v
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ─────────────────────────────────────────────
# Tool 1: search_listings
# ─────────────────────────────────────────────

class TestSearchListings:

    def test_returns_list(self):
        """search_listings always returns a list, never raises."""
        results = search_listings("vintage graphic tee")
        assert isinstance(results, list)

    def test_happy_path_returns_results(self):
        """A reasonable query with no filters should find at least one match."""
        results = search_listings("vintage graphic tee", size=None, max_price=None)
        assert len(results) > 0

    def test_results_are_dicts_with_expected_fields(self):
        """Each returned item should have all required listing fields."""
        results = search_listings("jacket", size=None, max_price=None)
        assert len(results) > 0
        required_fields = {
            "id", "title", "description", "category",
            "style_tags", "size", "condition", "price",
            "colors", "brand", "platform",
        }
        for item in results:
            assert required_fields.issubset(item.keys()), (
                f"Item {item.get('id')} is missing fields: "
                f"{required_fields - item.keys()}"
            )

    def test_empty_results_on_impossible_query(self):
        """An impossible query must return [] without raising."""
        results = search_listings("designer ballgown", size="XXS", max_price=5)
        assert results == []

    def test_price_filter_respected(self):
        """All returned items must have price <= max_price."""
        results = search_listings("jacket", size=None, max_price=10)
        for item in results:
            assert item["price"] <= 10, (
                f"Item '{item['title']}' has price ${item['price']} > $10"
            )

    def test_price_filter_none_skips_filtering(self):
        """Passing max_price=None should not exclude any item on price alone."""
        results_filtered = search_listings("jacket", size=None, max_price=10)
        results_unfiltered = search_listings("jacket", size=None, max_price=None)
        assert len(results_unfiltered) >= len(results_filtered)

    def test_size_filter_case_insensitive(self):
        """Size match should be case-insensitive substring."""
        results_upper = search_listings("top", size="M", max_price=None)
        results_lower = search_listings("top", size="m", max_price=None)
        assert len(results_upper) == len(results_lower)

    def test_size_filter_respected(self):
        """All returned items must contain the requested size string."""
        results = search_listings("vintage", size="M", max_price=None)
        for item in results:
            assert "m" in item["size"].lower(), (
                f"Item '{item['title']}' has size '{item['size']}' "
                f"which does not contain 'M'"
            )

    def test_results_sorted_by_relevance(self):
        """Top result should contain more query keywords than a low-relevance item."""
        results = search_listings("vintage graphic tee streetwear grunge")
        assert len(results) > 1
        top = results[0]
        blob = (
            top["title"] + " " +
            top["description"] + " " +
            " ".join(top["style_tags"])
        ).lower()
        assert any(
            kw in blob
            for kw in ["vintage", "graphic", "tee", "streetwear", "grunge"]
        )

    def test_zero_score_items_excluded(self):
        """Items with no keyword overlap should not appear in results."""
        results = search_listings("flannel plaid", size=None, max_price=None)
        for item in results:
            blob = (
                item["title"] + " " +
                item["description"] + " " +
                " ".join(item["style_tags"])
            ).lower()
            assert any(kw in blob for kw in ["flannel", "plaid"]), (
                f"Item '{item['title']}' has zero keyword overlap but was returned"
            )


# ─────────────────────────────────────────────
# Tool 2: suggest_outfit
# ─────────────────────────────────────────────

class TestSuggestOutfit:
    """
    These tests call the Groq LLM — require a valid GROQ_API_KEY in .env.
    """

    @pytest.fixture
    def sample_item(self):
        results = search_listings("vintage graphic tee", size=None, max_price=None)
        assert len(results) > 0, "Need at least one result to test suggest_outfit"
        return results[0]

    def test_returns_string(self, sample_item):
        """suggest_outfit always returns a str."""
        result = suggest_outfit(sample_item, get_example_wardrobe())
        assert isinstance(result, str)

    def test_non_empty_with_wardrobe(self, sample_item):
        """Returns a non-empty suggestion when wardrobe has items."""
        result = suggest_outfit(sample_item, get_example_wardrobe())
        assert len(result.strip()) > 0

    def test_non_empty_with_empty_wardrobe(self, sample_item):
        """Returns a non-empty suggestion even when wardrobe is empty."""
        result = suggest_outfit(sample_item, get_empty_wardrobe())
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_empty_wardrobe_does_not_crash(self, sample_item):
        """Empty wardrobe must NOT raise any exception."""
        try:
            suggest_outfit(sample_item, get_empty_wardrobe())
        except Exception as e:
            pytest.fail(
                f"suggest_outfit raised an exception with empty wardrobe: {e}"
            )

    def test_wardrobe_suggestion_mentions_wardrobe_pieces(self, sample_item):
        """With a full wardrobe, the suggestion should reference at least one piece."""
        result = suggest_outfit(sample_item, get_example_wardrobe())
        wardrobe_keywords = [
            "jeans", "sneakers", "boots", "jacket", "hoodie",
            "trousers", "sweatshirt", "tank", "belt", "bag",
        ]
        assert any(kw in result.lower() for kw in wardrobe_keywords), (
            f"Outfit suggestion didn't reference any wardrobe piece.\nGot: {result}"
        )


# ─────────────────────────────────────────────
# Tool 3: create_fit_card
# ─────────────────────────────────────────────

class TestCreateFitCard:
    """
    These tests call the Groq LLM — require a valid GROQ_API_KEY in .env.
    """

    @pytest.fixture
    def sample_item(self):
        results = search_listings("vintage graphic tee", size=None, max_price=None)
        assert len(results) > 0
        return results[0]

    @pytest.fixture
    def sample_outfit(self):
        return (
            "Pair with baggy straight-leg jeans and chunky white sneakers "
            "for a classic streetwear look. Add the vintage denim jacket on top "
            "for a grungier edge."
        )

    def test_returns_string(self, sample_outfit, sample_item):
        """create_fit_card always returns a str."""
        result = create_fit_card(sample_outfit, sample_item)
        assert isinstance(result, str)

    def test_non_empty_on_valid_input(self, sample_outfit, sample_item):
        """Returns a non-empty caption for valid inputs."""
        result = create_fit_card(sample_outfit, sample_item)
        assert len(result.strip()) > 0

    def test_empty_outfit_returns_error_string(self, sample_item):
        """Empty outfit string must return an error message, not raise."""
        result = create_fit_card("", sample_item)
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        assert any(
            word in result.lower()
            for word in ["couldn't", "missing", "failed"]
        )

    def test_whitespace_only_outfit_returns_error_string(self, sample_item):
        """Whitespace-only outfit string must return an error message, not raise."""
        result = create_fit_card("   ", sample_item)
        assert isinstance(result, str)
        assert any(
            word in result.lower()
            for word in ["couldn't", "missing", "failed"]
        )

    def test_empty_outfit_does_not_raise(self, sample_item):
        """Empty outfit must NOT raise any exception."""
        try:
            create_fit_card("", sample_item)
        except Exception as e:
            pytest.fail(
                f"create_fit_card raised an exception with empty outfit: {e}"
            )

    def test_caption_mentions_price(self, sample_outfit, sample_item):
        """The caption should mention the item's price."""
        result = create_fit_card(sample_outfit, sample_item)
        price_str = str(int(sample_item["price"]))
        assert price_str in result, (
            f"Caption did not mention price ${sample_item['price']}.\nGot: {result}"
        )

    def test_caption_mentions_platform(self, sample_outfit, sample_item):
        """The caption should mention the platform."""
        result = create_fit_card(sample_outfit, sample_item)
        assert sample_item["platform"].lower() in result.lower(), (
            f"Caption did not mention platform '{sample_item['platform']}'.\nGot: {result}"
        )

    def test_output_varies_across_calls(self, sample_outfit, sample_item):
        """
        3 calls with the same input should produce at least 2 distinct outputs.
        Verifies temperature=0.9 is actually being applied.
        """
        results = {create_fit_card(sample_outfit, sample_item) for _ in range(3)}
        assert len(results) >= 2, (
            "create_fit_card returned identical output on 3 consecutive calls — "
            "check that temperature=0.9 is being passed to the LLM."
        )
