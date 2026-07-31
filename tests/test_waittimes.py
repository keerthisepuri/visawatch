"""Parsing and diffing the State Department wait-times table.

The fixtures below reproduce the real page as it was read on 31 July 2026:
values are given in months (sometimes fractional, sometimes "< 0.5 Month"),
and the date reads "Last Updated: 15-APRIL-2026".
"""

from visawatch import waittimes as wt

PAGE_TEXT = (
    "Global Visa Wait Times\n"
    'Last Updated: "15-APRIL-2026"\n'
    "Wait times for interview appointments vary by location.\n"
)

# City/Post | B1/B2 avg | B1/B2 next | F,M,J next | Petition-Based next | Crew/Transit next
ROWS = [
    ["City/Post", "Average wait times", "Next available appointment",
     "Next available appointment", "Next available appointment", "Next available appointment"],
    ["New Delhi", "5 Months", "7 Months", "1 Month", "1 Month", "1 Month"],
    ["Mumbai (Bombay)", "7 Months", "7.5 Months", "2.5 Months", "1 Month", "1 Month"],
    ["Chennai (Madras)", "4 Months", "4 Months", "1 Month", "3.5 Months", "2 Months"],
    ["Hyderabad", "5 Months", "8 Months", "2.5 Months", "3 Months", "< 0.5 Month"],
    ["Kolkata", "7 Months", "7 Months", "3.5 Months", "1 Month", "NA"],
    ["Toronto", "10 Days", "20 Days", "5 Days", "7 Days", "2 Days"],
]

POSTS = ["New Delhi", "Mumbai (Bombay)", "Chennai (Madras)", "Hyderabad", "Kolkata"]


def test_reads_petition_column_for_indian_posts():
    result = wt.extract(PAGE_TEXT, ROWS, POSTS)
    assert result.last_updated == "15-APRIL-2026"
    assert result.posts == {
        "New Delhi": "1 Month",
        "Mumbai (Bombay)": "1 Month",
        "Chennai (Madras)": "3.5 Months",
        "Hyderabad": "3 Months",
        "Kolkata": "1 Month",
    }
    assert "Toronto" not in result.posts


def test_tolerates_short_post_names():
    rows = [ROWS[0], ["Mumbai", "7 Months", "7.5 Months", "2.5 Months", "2 Months", "1 Month"]]
    result = wt.extract(PAGE_TEXT, rows, POSTS)
    assert result.posts["Mumbai (Bombay)"] == "2 Months"


def test_detects_improvement_and_last_updated_change():
    previous = {
        "last_updated": "01-MARCH-2026",
        "posts": {
            "Hyderabad": "6 Months",       # improves to 3 Months
            "New Delhi": "1 Month",        # unchanged
            "Chennai (Madras)": "2 Months",  # gets worse -> 3.5 Months
        },
    }
    current = wt.extract(PAGE_TEXT, ROWS, POSTS)
    changes = wt.compare(previous, current)
    joined = "\n".join(changes)

    assert "Last updated" in joined and "15-APRIL-2026" in joined
    assert "IMPROVED  Hyderabad: 6 Months -> 3 Months (3 months sooner)" in changes
    assert not any("New Delhi" in c for c in changes)                       # unchanged
    assert any("Chennai" in c and not c.startswith("IMPROVED") for c in changes)  # worse


def test_no_changes_when_nothing_moved():
    current = wt.extract(PAGE_TEXT, ROWS, POSTS)
    assert wt.compare(current.to_dict(), current) == []


def test_first_ever_run_reports_no_false_changes():
    current = wt.extract(PAGE_TEXT, ROWS, POSTS)
    assert wt.compare({}, current) == []


def test_parse_days_handles_every_unit_the_page_uses():
    assert wt.parse_days("5 Months") == 150.0
    assert wt.parse_days("3.5 Months") == 105.0
    assert wt.parse_days("1 Month") == 30.0
    assert wt.parse_days("2 Weeks") == 14.0
    assert wt.parse_days("45 Days") == 45.0
    assert wt.parse_days("< 0.5 Month") == pytest_approx(15.0)
    assert wt.parse_days("NA") is None
    assert wt.parse_days("") is None


def test_less_than_counts_as_better_than_the_plain_value():
    assert wt.parse_days("< 0.5 Month") < wt.parse_days("0.5 Month")


def pytest_approx(value):
    import pytest
    return pytest.approx(value, abs=0.05)
