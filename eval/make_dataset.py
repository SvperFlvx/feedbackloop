"""How items.json was born: 94 items across 10 screens.

items.json is the source of truth, not this script. The harness only reads that
file, and the gold grouping in it was re-cut by hand on 21 November 2026 when
the original seven themes turned out to be feature areas rather than user
intents — two of them were containers holding three unrelated problems each.

The theme labels in ROWS below are the SUPERSEDED ones. Running this script
would undo the re-cut, so it refuses to overwrite an existing items.json. Edit
items.json directly, or delete it deliberately if you really mean to start over.
"""

import json
import pathlib
import sys

PEOPLE = [
    "Maya Chen", "Jon Bell", "Aisha Patel", "Lewis Morgan", "Tess Howard",
    "Owen King", "Priya Raman", "Dan Weiss", "Lena Fischer", "Marco Silva",
    "Ruth Adeyemi", "Sam Okafor",
]

# (theme, screen, type, build, text)
ROWS = [
    # ---- Checkout feels confusing (18) -----------------------------------
    ("Checkout feels confusing", "Cart", "question", "1.8.4", "I can't tell if the cart saved my changes or not."),
    ("Checkout feels confusing", "Cart", "bug", "1.8.4", "Updating the quantity doesn't change the total until I reload."),
    ("Checkout feels confusing", "Cart", "improvement", "1.8.3", "There should be a way to see the full order summary before I start checking out."),
    ("Checkout feels confusing", "Cart", "question", "1.8.4", "Is the number at the bottom with tax or without? It isn't labelled."),
    ("Checkout feels confusing", "Checkout", "improvement", "1.8.4", "I kept looking for a promo code field. It would help to show it before the payment step."),
    ("Checkout feels confusing", "Checkout", "bug", "1.8.4", "The total changed after I selected express delivery and I didn't understand why."),
    ("Checkout feels confusing", "Checkout", "question", "1.8.4", "Which step am I on? There's no indication of how many are left."),
    ("Checkout feels confusing", "Checkout", "improvement", "1.8.4", "Let me go back a step without losing what I already typed."),
    ("Checkout feels confusing", "Checkout", "bug", "1.8.3", "Pressing back took me all the way out of checkout and emptied the form."),
    ("Checkout feels confusing", "Checkout", "question", "1.8.4", "I don't know what happens when I press Continue. Does it charge me?"),
    ("Checkout feels confusing", "Checkout", "improvement", "1.8.4", "The button says Continue on every screen so I never know what's coming next."),
    ("Checkout feels confusing", "Checkout", "bug", "1.8.4", "The order summary collapsed on its own and I couldn't get it back."),
    ("Checkout feels confusing", "Checkout", "improvement", "1.8.3", "Show me the final amount at every step, not just at the end."),
    ("Checkout feels confusing", "Delivery", "question", "1.8.4", "Is express delivery guaranteed or just an estimate? It isn't clear."),
    ("Checkout feels confusing", "Delivery", "improvement", "1.8.4", "I'd like to see the delivery cost before I pick an option, not after."),
    ("Checkout feels confusing", "Delivery", "bug", "1.8.3", "Choosing standard delivery sometimes resets my address selection."),
    ("Checkout feels confusing", "Payment", "question", "1.8.4", "Am I done? The screen just sat there after I pressed Pay."),
    ("Checkout feels confusing", "Payment", "improvement", "1.8.4", "Tell me what I'm being charged right next to the Pay button."),

    # ---- Payment confidence (15) -----------------------------------------
    ("Payment confidence", "Checkout", "question", "1.8.3", "Do you store my card? I couldn't find anything that said either way."),
    ("Payment confidence", "Checkout", "improvement", "1.8.3", "A line about security near the card field would make me more comfortable."),
    ("Payment confidence", "Checkout", "bug", "1.8.3", "It said my card was declined but the bank app showed the charge went through."),
    ("Payment confidence", "Payment", "bug", "1.8.3", "Apple Pay failed twice and then my card worked straight away."),
    ("Payment confidence", "Payment", "question", "1.8.3", "Why do you need the billing address again? I already entered it."),
    ("Payment confidence", "Payment", "bug", "1.8.3", "The card form rejected a perfectly valid number three times."),
    ("Payment confidence", "Payment", "improvement", "1.8.3", "Show which cards are accepted before I start typing one in."),
    ("Payment confidence", "Payment", "question", "1.8.2", "Is this page secure? There's no padlock or anything like it."),
    ("Payment confidence", "Payment", "bug", "1.8.3", "I got charged but no confirmation email arrived for twenty minutes."),
    ("Payment confidence", "Payment", "improvement", "1.8.3", "Let me save a card for next time. Typing it every order is tedious."),
    ("Payment confidence", "Payment", "question", "1.8.3", "What happens if the payment fails halfway? Do I lose the order?"),
    ("Payment confidence", "Payment", "bug", "1.8.2", "The CVV field wouldn't accept my input on the first try."),
    ("Payment confidence", "Payment", "improvement", "1.8.3", "The error just said invalid. Tell me which field is wrong."),
    ("Payment confidence", "Payment", "praise", "1.8.3", "Apple Pay was quick once it worked. That part felt reassuring."),
    ("Payment confidence", "Delivery", "question", "1.8.3", "If delivery changes the price, when exactly am I charged?"),

    # ---- Dark mode requests (13) -----------------------------------------
    ("Dark mode requests", "Settings", "improvement", "1.8.1", "Please add a dark mode. I shop in bed and this is blinding."),
    ("Dark mode requests", "Settings", "improvement", "1.8.1", "A theme setting would be great, even just follow-the-system."),
    ("Dark mode requests", "Settings", "question", "1.8.1", "Is dark mode planned? I couldn't find it anywhere in settings."),
    ("Dark mode requests", "Settings", "improvement", "1.8.1", "Every other app I use has a dark theme now."),
    ("Dark mode requests", "Settings", "improvement", "1.8.0", "Let the app follow my phone's appearance setting automatically."),
    ("Dark mode requests", "Home", "improvement", "1.8.1", "The white background at night is really harsh on the eyes."),
    ("Dark mode requests", "Home", "improvement", "1.8.1", "Dark mode would make the product photos stand out more."),
    ("Dark mode requests", "Home", "question", "1.8.0", "Does this support dark mode? It stays white for me."),
    ("Dark mode requests", "Checkout", "improvement", "1.8.1", "Checkout is the brightest screen in the app at night."),
    ("Dark mode requests", "Checkout", "improvement", "1.8.1", "A darker theme here would be easier to read in low light."),
    ("Dark mode requests", "Addresses", "improvement", "1.8.1", "The address list is a wall of white. Dark mode would help."),
    ("Dark mode requests", "Product", "improvement", "1.8.1", "Product pages would look much better on a dark background."),
    ("Dark mode requests", "Product", "improvement", "1.8.0", "Add dark mode, the photos get washed out against all that white."),

    # ---- Onboarding friction (12) ----------------------------------------
    ("Onboarding friction", "Onboarding", "improvement", "1.8.2", "Asking me to create an account before I can look around put me off."),
    ("Onboarding friction", "Onboarding", "question", "1.8.2", "Why do you need my phone number just to browse?"),
    ("Onboarding friction", "Onboarding", "bug", "1.8.2", "The verification code took four minutes to arrive and then expired."),
    ("Onboarding friction", "Onboarding", "improvement", "1.8.2", "Let me skip the tour. I just wanted to find one thing."),
    ("Onboarding friction", "Onboarding", "bug", "1.8.2", "The keyboard covered the password field and I couldn't scroll."),
    ("Onboarding friction", "Onboarding", "improvement", "1.8.2", "Four screens before I saw a single product is three too many."),
    ("Onboarding friction", "Onboarding", "question", "1.8.1", "What are the notification permissions actually for? It asked immediately."),
    ("Onboarding friction", "Onboarding", "bug", "1.8.2", "Sign in with Apple bounced me back to the start twice."),
    ("Onboarding friction", "Onboarding", "improvement", "1.8.1", "Ask for the permissions when you need them, not all at once up front."),
    ("Onboarding friction", "Home", "question", "1.8.2", "After signing up I landed somewhere I didn't recognise. Where am I?"),
    ("Onboarding friction", "Home", "improvement", "1.8.2", "Nothing explained what to do first once I got in."),
    ("Onboarding friction", "Home", "bug", "1.8.1", "The welcome banner wouldn't dismiss and covered the first row."),

    # ---- Address management (11) -----------------------------------------
    ("Address management", "Addresses", "improvement", "1.8.4", "This new saved addresses flow is so much faster. Really nice update!"),
    ("Address management", "Addresses", "question", "1.8.4", "Can I change the delivery address after placing the order?"),
    ("Address management", "Addresses", "bug", "1.8.4", "Editing an address created a duplicate instead of replacing it."),
    ("Address management", "Addresses", "improvement", "1.8.4", "Let me label addresses. Home and Work would be enough."),
    ("Address management", "Addresses", "bug", "1.8.3", "My default address keeps reverting to an old one I deleted."),
    ("Address management", "Addresses", "improvement", "1.8.4", "Postcode lookup would save a lot of typing here."),
    ("Address management", "Addresses", "praise", "1.8.4", "Good that it remembered my address from last time."),
    ("Address management", "Checkout", "bug", "1.8.4", "The address picker showed addresses I'd already removed."),
    ("Address management", "Checkout", "improvement", "1.8.4", "I'd like to add a new address without leaving checkout."),
    ("Address management", "Delivery", "question", "1.8.4", "Does changing the address here change it on my account too?"),
    ("Address management", "Delivery", "bug", "1.8.3", "It delivered the old address even though I changed it at checkout."),

    # ---- Search results quality (13) -------------------------------------
    ("Search results quality", "Search", "bug", "1.8.4", "Searching for the exact product name returns nothing."),
    ("Search results quality", "Search", "improvement", "1.8.4", "Let me filter by size without opening three menus."),
    ("Search results quality", "Search", "bug", "1.8.4", "Results change order every time I come back to them."),
    ("Search results quality", "Search", "question", "1.8.4", "How is this sorted? It doesn't look like relevance."),
    ("Search results quality", "Search", "improvement", "1.8.4", "Spelling it slightly wrong gives zero results. Be more forgiving."),
    ("Search results quality", "Search", "bug", "1.8.3", "Out of stock items are mixed in with everything else."),
    ("Search results quality", "Search", "improvement", "1.8.4", "Show how many results there are, not just an endless scroll."),
    ("Search results quality", "Search", "bug", "1.8.4", "Clearing a filter also cleared my search term."),
    ("Search results quality", "Search", "improvement", "1.8.3", "Recent searches would save me retyping the same thing."),
    ("Search results quality", "Search", "question", "1.8.4", "Why does the same search give different results on wifi and data?"),
    ("Search results quality", "Home", "improvement", "1.8.4", "The search box is hidden behind an icon. Make it visible."),
    ("Search results quality", "Home", "question", "1.8.3", "Are the recommendations personalised or the same for everyone?"),
    ("Search results quality", "Product", "bug", "1.8.4", "Tapping a result sometimes opens a different product."),

    # ---- Performance complaints (12) -------------------------------------
    ("Performance complaints", "Home", "bug", "1.8.2", "The home screen takes five or six seconds to show anything."),
    ("Performance complaints", "Home", "bug", "1.8.2", "Images load one by one and the layout jumps around while they do."),
    ("Performance complaints", "Home", "question", "1.8.1", "Is it meant to be this slow on an older phone?"),
    ("Performance complaints", "Search", "bug", "1.8.2", "There's a long pause after I type before anything happens."),
    ("Performance complaints", "Search", "bug", "1.8.2", "Scrolling the results stutters badly once I'm a page or two down."),
    ("Performance complaints", "Product", "bug", "1.8.2", "The product page takes ages to open from the list."),
    ("Performance complaints", "Product", "bug", "1.8.2", "Swiping between photos is laggy."),
    ("Performance complaints", "Product", "bug", "1.8.1", "The app froze for a few seconds when I zoomed into an image."),
    ("Performance complaints", "Product", "improvement", "1.8.2", "Load a low-res photo first so there's something to look at."),
    ("Performance complaints", "Checkout", "bug", "1.8.2", "There's a noticeable delay between each checkout step."),
    ("Performance complaints", "Checkout", "bug", "1.8.1", "The spinner stayed on screen long enough that I nearly gave up."),
    ("Performance complaints", "Payment", "bug", "1.8.2", "Confirming payment hung for about ten seconds with no feedback."),
]


def build():
    items = []
    for n, (theme, screen, type_, build_label, text) in enumerate(ROWS):
        items.append({
            "id": f"i{n + 1:03d}",
            "text": text,
            "screen": screen,              # the owner-facing screen name
            "raw_screen_key": screen.lower().replace(" ", "_") + "_screen",
            "author": PEOPLE[n % len(PEOPLE)],
            "build": build_label,
            "gold_type": type_,            # withheld from the model
            "gold_theme": theme,           # withheld from the model
        })
    return items


if __name__ == "__main__":
    items = build()
    out = pathlib.Path(__file__).parent / "dataset" / "items.json"
    if out.exists():
        sys.exit(
            f"{out} already exists and this script would overwrite it with the\n"
            "superseded seven-theme grouping. items.json is the source of truth.\n"
            "Delete it first if you genuinely mean to start the fixture over."
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, indent=2) + "\n")

    themes = {}
    screens = {}
    for it in items:
        themes[it["gold_theme"]] = themes.get(it["gold_theme"], 0) + 1
        screens[it["screen"]] = screens.get(it["screen"], 0) + 1

    print(f"wrote {len(items)} items to {out}")
    print("\nthemes:")
    for k, v in sorted(themes.items(), key=lambda kv: -kv[1]):
        print(f"  {v:3d}  {k}")
    print("\nscreens:")
    for k, v in sorted(screens.items(), key=lambda kv: -kv[1]):
        print(f"  {v:3d}  {k}")
