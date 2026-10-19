import pytest

from parser import extract_mpt_dict, parse_day_string

SAMPLE_HTML = """
<script>
var MPT = {
  20261018: "144805060553061507191233130015311545180618111926194512301315",
  20261019: "144805070555061507211233130015291545180418091924194512301315"
};
</script>
"""


def test_extract_mpt_dict_success():
    result = extract_mpt_dict(SAMPLE_HTML)
    assert len(result) == 2
    assert "20261018" in result
    assert len(result["20261018"]) == 60


def test_extract_mpt_dict_missing_raises():
    with pytest.raises(ValueError, match="MPT dictionary not found"):
        extract_mpt_dict("<html><body>No schedule here</body></html>")


def test_parse_day_string_60_chars():
    raw = "144805060553061507191233130015311545180618111926194512301315"
    sched = parse_day_string("20261018", raw)
    assert sched.hijri_date == "1448-05-06"
    assert sched.fajr_azan == "2026-10-18T05:53:00-04:00"
    assert sched.fajr_iqama == "2026-10-18T06:15:00-04:00"
    assert sched.jumah_1 == "2026-10-18T12:30:00-04:00"
    assert sched.jumah_2 == "2026-10-18T13:15:00-04:00"


def test_parse_day_string_invalid_length():
    with pytest.raises(ValueError, match="Invalid MPT string format"):
        parse_day_string("20261018", "12345")