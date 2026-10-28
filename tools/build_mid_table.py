"""Build bundled country lookup from a locally downloaded ITU allocation table."""
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and len(self.row) == 2:
            self.rows.append(self.row)


if __name__ == "__main__":
    parser = TableParser()
    parser.feed(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
    countries = {}
    for codes, country in parser.rows:
        for code in re.findall(r"\b[2-7]\d{2}\b", codes):
            countries[code] = country
    assert len(countries) > 250, f"Unexpected table size: {len(countries)}"
    assert countries["368"] == "United States of America"
    result = {"source": "https://www.itu.int/gladapp/Allocation/MIDs",
              "retrieved": "2026-10-27", "countries": dict(sorted(countries.items()))}
    target = Path(__file__).resolve().parents[1] / "data" / "mid-countries.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(countries)} MID assignments")
