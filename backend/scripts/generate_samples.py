"""Generate NEXUS AI's synthetic demonstration content (deterministic, seed 42).

Everything produced here is fictional and written for this project; it is released with the repository's
MIT license. Companies, products and figures are invented.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[2] / "samples"
REGIONS = {"North America": 1.25, "Europe": 1.0, "Asia Pacific": 1.1, "Latin America": 0.55}
PRODUCTS = {"Atlas Sensor": 189.0, "Beacon Hub": 449.0, "Cirrus Cloud Plan": 39.0, "Delta Edge Kit": 899.0}
CHANNELS = ["Online", "Partner", "Direct"]


def sales_csv() -> Path:
    rng = random.Random(42)
    out = ROOT / "datasets" / "synthetic_sales_2023_2025.csv"
    lines = ["order_date,region,product,channel,units,unit_price,revenue,discount_pct,customer_rating"]
    d = date(2023, 1, 1)
    while d <= date(2025, 12, 31):
        season = 1 + 0.28 * math.sin(2 * math.pi * (d.timetuple().tm_yday - 80) / 365)  # spring/summer peak
        holiday = 1.6 if d.month == 12 and d.day > 10 else (1.3 if d.month == 11 and d.day > 20 else 1.0)
        growth = 1 + 0.18 * ((d - date(2023, 1, 1)).days / 365)
        for region, rw in REGIONS.items():
            for product, price in PRODUCTS.items():
                if rng.random() > 0.55:
                    continue
                shock = 0.45 if (region == "Europe" and date(2024, 7, 1) <= d <= date(2024, 8, 15)) else 1.0
                units = max(1, int(rng.gauss(14, 4) * season * holiday * growth * rw * shock))
                discount = rng.choice([0, 0, 0, 5, 10, 15])
                p = round(price * (1 - discount / 100), 2)
                rating = round(min(5.0, max(1.0, rng.gauss(4.2 if product != "Beacon Hub" else 3.8, 0.5))), 1)
                lines.append(f"{d.isoformat()},{region},{product},{rng.choice(CHANNELS)},{units},{p},"
                             f"{round(units * p, 2)},{discount},{rating}")
        d += timedelta(days=1)
    out.write_text("\n".join(lines) + "\n")
    return out


WHITEPAPER = [
    ("Abstract", "This whitepaper describes Helios Grid, a fictional modular battery storage platform designed by "
     "the invented company Northwind Energy Labs. It is synthetic demonstration content for NEXUS AI and does not "
     "describe a real product."),
    ("1. Problem", "Commercial buildings waste between 12 and 18 percent of on-site solar generation because "
     "production peaks at midday while demand peaks in the early evening. Helios Grid stores midday surplus and "
     "discharges it between 5 pm and 9 pm."),
    ("2. Architecture", "Each Helios Grid cabinet contains eight lithium iron phosphate modules of 6.4 kWh, for a "
     "usable capacity of 51.2 kWh per cabinet. Up to twelve cabinets can be chained, giving a maximum installation "
     "of 614.4 kWh. A cabinet weighs 540 kg and occupies 0.9 square metres of floor space."),
    ("3. Performance", "In a 14-month pilot at three sites, round-trip efficiency averaged 91.3 percent. The pilot "
     "reduced peak grid demand by 37 percent and cut annual electricity costs by an average of 22 percent. The "
     "battery management system kept cell temperatures between 18 and 32 degrees Celsius."),
    ("4. Safety", "The modules use lithium iron phosphate chemistry, which has a higher thermal runaway threshold "
     "than nickel manganese cobalt cells. Every cabinet includes aerosol fire suppression, per-module fuses and a "
     "sealed IP55 enclosure."),
    ("5. Pricing and warranty", "List price is 19,800 US dollars per cabinet before installation. Northwind Energy "
     "Labs offers a 10-year warranty guaranteeing at least 80 percent of original capacity, or 6,000 full cycles, "
     "whichever comes first."),
    ("6. Limitations", "Helios Grid is not designed for off-grid residential use, and the pilot sites were all in "
     "temperate climates. Performance in regions with sustained temperatures above 40 degrees Celsius has not "
     "been measured."),
]


def whitepaper_pdf() -> Path:
    out = ROOT / "documents" / "helios-grid-whitepaper.pdf"
    pdf = FPDF(format="A4")
    pdf.set_title("Helios Grid Technical Whitepaper (synthetic)")
    pdf.set_author("NEXUS AI sample content")
    pdf.set_margins(20, 20, 20)
    for i, (heading, body) in enumerate(WHITEPAPER):
        if i in (0, 3, 5):
            pdf.add_page()
            if i == 0:
                pdf.set_font("Helvetica", "B", 20)
                pdf.multi_cell(0, 10, "Helios Grid: Modular Commercial Battery Storage", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "I", 10)
                pdf.multi_cell(0, 6, "Synthetic demonstration document - fictional company and product", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(6)
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, body, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    for p in (sales_csv(), whitepaper_pdf()):
        print("wrote", p.relative_to(ROOT.parent), p.stat().st_size, "bytes")
