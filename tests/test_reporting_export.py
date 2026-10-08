"""Unit tests for the exportable compliance summaries (Unit 6).

The CSV builders take plain values and return plain values, so these tests
need no database and no request. The injection tests are black-box: they
state what a spreadsheet must never be handed, whatever the implementation.
"""
import csv
import io

import pytest

from src.reporting_dashboard import export


@pytest.mark.blackbox
@pytest.mark.parametrize("hostile", ["=HYPERLINK(\"http://x\",\"y\")", "+1+1",
                                     "-2+3", "@SUM(A1:A9)", "\t=1", "\r=1"])
def test_a_cell_a_spreadsheet_would_run_as_a_formula_is_neutralised(hostile):
    assert export.csv_safe(hostile) == "'" + hostile


@pytest.mark.blackbox
@pytest.mark.parametrize("ordinary", ["1-1-1", "Control Owner 01", "Implemented", ""])
def test_ordinary_text_is_left_alone(ordinary):
    assert export.csv_safe(ordinary) == ordinary


@pytest.mark.whitebox
def test_numbers_are_never_rewritten():
    assert export.csv_safe(-3) == -3 and export.csv_safe(42.5) == 42.5


def _summary():
    return {
        "implementation": {"score": 40.0},
        "by_domain": [
            {"domain": "Cybersecurity Resilience", "assessed": 4, "excluded": 0,
             "score": 31.2},
            {"domain": "Cybersecurity Governance", "assessed": 31, "excluded": 4,
             "score": 42.7},
        ],
        "domain_gaps": {
            "Cybersecurity Resilience": {"evidenced": 0, "missing_evidence": 4,
                                         "open": 1, "overdue": 0, "exposure_index": 0},
            "Cybersecurity Governance": {"evidenced": 9, "missing_evidence": 22,
                                         "open": 4, "overdue": 3, "exposure_index": 14},
        },
    }


@pytest.mark.whitebox
def test_domain_rows_keep_the_weakest_first_order_and_add_a_total():
    rows = export.domain_rows(_summary(), {"Cybersecurity Governance": 0})
    assert [r[0] for r in rows] == ["Cybersecurity Resilience",
                                    "Cybersecurity Governance", "All tracked domains"]
    total = rows[-1]
    assert total[1:5] == [39, 35, 4, 0]           # tracked, assessed, excluded, catalogue
    assert total[5] == 40.0                       # overall score, not a sum
    assert total[6:] == [9, 26, 5, 3, 14]


@pytest.mark.blackbox
def test_every_export_opens_with_the_no_certification_boundary():
    text = export.render_csv("Title", "Generated now", ["A"], [["x"]])
    lines = text.splitlines()
    assert lines[0] == "# Title"
    assert "does not certify" in lines[2]
    assert lines[3] == "A"


@pytest.mark.blackbox
def test_the_rendered_file_parses_as_csv_and_carries_no_live_formula():
    text = export.render_csv("T", "G", ["Owner"], [["=cmd|' /C calc'!A0"]])
    body = [ln for ln in text.splitlines() if not ln.startswith("#")]
    rows = list(csv.reader(io.StringIO("\n".join(body))))
    assert rows[1][0].startswith("'=")
