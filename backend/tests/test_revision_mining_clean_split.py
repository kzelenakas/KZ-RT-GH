"""Clean/split preprocessing for raw revision-request text.
Ported from the anthropic-skills revision-request-parser skill (Clean-4.7 + Splitv4.11).
Synthetic examples only — no real revision text (which may contain borrower PII).
"""

from app.revision_mining.clean_split import clean_revision_text, split_revision_text


def test_clean_strips_email_boilerplate_and_signoff():
    raw = (
        "Good morning,\n\n"
        "Please review the attached information as it pertains to a Reconsideration of Value request.\n"
        "The subject site has adverse external influence not addressed.\n\n"
        "Thank you,\nJohn"
    )
    cleaned = clean_revision_text(raw)
    assert cleaned is not None
    assert "adverse external influence" in cleaned
    assert "Good morning" not in cleaned
    assert "Thank you" not in cleaned


def test_clean_drops_junk_only_cells():
    assert clean_revision_text("N/A") is None
    assert clean_revision_text("See attached") is None
    assert clean_revision_text("") is None
    assert clean_revision_text(None) is None


def test_split_breaks_numbered_bundle_into_items():
    text = "1. Correct the ZIP code on the subject address.\n2. Provide support for the site adjustment.\n3. Add the missing comparable photo."
    items = split_revision_text(text)
    assert len(items) == 3
    assert items[0].startswith("Correct the ZIP code")
    assert items[1].startswith("Provide support for the site adjustment")
    assert items[2].startswith("Add the missing comparable photo")


def test_split_protects_addresses_from_being_split():
    text = "Please correct the comparable address.\n123 Main St, Springfield, IL 62704\nAdd the missing photo."
    items = split_revision_text(text)
    joined = " ".join(items)
    assert "123 Main St" in joined
    # The address line must not become its own orphan action item when it has no verb:
    assert not any(item.strip().startswith("123 Main St") and len(item.split()) < 4 for item in items)
