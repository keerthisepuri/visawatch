"""Word matching against the messy way people actually write these posts."""

from visawatch.matcher import match, normalize, tighten


def test_slash_separated_cities_still_match(cfg):
    """'HYD/DEL slots dropped' style posts are extremely common."""
    assert match("Bulk slots dropped Hyderabad/Chennai today", cfg).matched is True
    assert match("Delhi/Mumbai slots available now", cfg).matched is True
    assert match("slots dropped for Kolkata,Chennai", cfg).matched is True


def test_missing_spaces_after_punctuation_still_match(cfg):
    assert match("SLOTS DROPPED!!Hyderabad H1B", cfg).matched is True
    assert match("Slots open...Mumbai", cfg).matched is True


def test_hyphenated_and_dotted_visa_classes_still_boost(cfg):
    for text in (
        "Slots dropped Hyderabad H-1B",
        "Slots dropped Hyderabad H.1.B",
        "Slots dropped Hyderabad h1b",
    ):
        result = match(text, cfg)
        assert result.matched is True
        assert result.high_priority is True, text


def test_word_boundaries_are_respected(cfg):
    # "India" must not match inside "Indiana", and "slot" must not match "slots"
    # only via a substring of an unrelated word.
    assert match("Slots opened in Indiana", cfg).matched is False
    assert match("The applicants slotted into Delhi opened files", cfg).group_a == []


def test_exclusions_cancel_a_match(cfg):
    assert match("No slots available for Hyderabad today", cfg).matched is False
    assert match("When will slots open for Chennai?", cfg).matched is False


def test_two_normal_forms(cfg):
    assert normalize("H-1B/Delhi") == "h 1b delhi"
    assert tighten("H-1B/Delhi") == "h1bdelhi"
