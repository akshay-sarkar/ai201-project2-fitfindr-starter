"""
app.py — Gradio interface for FitFindr

Run with: python app.py
Then open the URL it prints (usually localhost:7860).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


def handle_query(user_query: str, wardrobe_choice: str):
    """
    Main handler — called when the user submits a query.
    Returns 5 strings mapped to the 5 output panels:
        listing_output, outfit_output, fitcard_output, price_output, retry_output
    """
    if not user_query or not user_query.strip():
        return "Please enter a search query to get started.", "", "", "", ""

    wardrobe = (
        get_empty_wardrobe()
        if wardrobe_choice == "Empty wardrobe (new user)"
        else get_example_wardrobe()
    )

    session = run_agent(user_query.strip(), wardrobe)

    # error path — show message in listing panel, clear everything else
    if session["error"]:
        return session["error"], "", "", "", ""

    # format the listing for the first panel
    item      = session["selected_item"]
    brand_str = f"Brand:     {item['brand']}\n" if item.get("brand") else ""

    listing_text = (
        f"{item['title']}\n"
        f"{'─' * 40}\n"
        f"Price:     ${item['price']:.2f}\n"
        f"Platform:  {item['platform']}\n"
        f"Size:      {item['size']}\n"
        f"Condition: {item['condition']}\n"
        f"{brand_str}"
        f"Colors:    {', '.join(item.get('colors', []))}\n"
        f"Tags:      {', '.join(item.get('style_tags', []))}\n"
        f"{'─' * 40}\n"
        f"{item['description']}"
    )

    # price comparison panel
    pc = session.get("price_comparison") or {}
    if pc.get("verdict") and pc["verdict"] != "unknown":
        verdict_emoji = {
            "great deal":       "🟢",
            "fair price":       "🟡",
            "on the high side": "🔴",
        }.get(pc["verdict"], "⚪")
        price_info = (
            f"{verdict_emoji} {pc['verdict'].upper()}\n"
            f"{'─' * 40}\n"
            f"{pc['message']}\n\n"
            f"Category avg:  ${pc['avg_price']:.2f}\n"
            f"Range:         ${pc['min_price']:.2f} – ${pc['max_price']:.2f}\n"
            f"Comparables:   {pc['count']} listings"
        )
    else:
        price_info = pc.get("message", "Price comparison unavailable.")

    retry_notice = session.get("retry_message") or ""

    return listing_text, session["outfit_suggestion"], session["fit_card"], price_info, retry_notice


def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        retry_output = gr.Textbox(
            label="⚠️ Search adjusted",
            lines=2,
            interactive=False,
        )

        with gr.Row():
            listing_output = gr.Textbox(label="🛍️ Top listing found", lines=10, interactive=False)
            outfit_output  = gr.Textbox(label="👗 Outfit idea",        lines=10, interactive=False)
            fitcard_output = gr.Textbox(label="✨ Your fit card",       lines=10, interactive=False)

        price_output = gr.Textbox(label="💰 Price check", lines=7, interactive=False)

        gr.Examples(
            examples=[
                ["vintage graphic tee under $30", "Example wardrobe"],
                ["90s track jacket in size M", "Example wardrobe"],
                ["flowy midi skirt under $40", "Example wardrobe"],
                ["black combat boots size 8", "Example wardrobe"],
                ["designer ballgown size XXS under $5", "Example wardrobe"],
                ["vintage tee size XXS under $5", "Example wardrobe"],
            ],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        outputs = [listing_output, outfit_output, fitcard_output, price_output, retry_output]

        submit_btn.click(fn=handle_query, inputs=[query_input, wardrobe_choice], outputs=outputs)
        query_input.submit(fn=handle_query, inputs=[query_input, wardrobe_choice], outputs=outputs)

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
