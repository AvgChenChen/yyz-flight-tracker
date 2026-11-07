import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from search import _sort_results


def test_nonstop_is_not_treated_as_missing():
    rows = [{"id": "one", "stops": 1}, {"id": "unknown", "stops": None},
            {"id": "direct", "stops": 0}, {"id": "missing"}]
    assert [r["id"] for r in _sort_results(rows, "fewest_stops")] == ["direct", "one", "unknown", "missing"]
    assert rows[0]["id"] == "one"
