"""Generate trip_plan.pdf - the detailed multi-city travel plan test fixture."""
import pathlib

HERE = pathlib.Path(__file__).parent
OUT = HERE / "trip_plan.pdf"

TEXT_LINES = [
    "TRAVEL PLAN - Autumn 2026 Multi-City Trip",
    "",
    "Traveler: 1 adult, economy class",
    "Start location: Lahore, Pakistan (LHE)",
    "Trip type: round trip (must return to Lahore)",
    "Total budget for flights + hotels: 3,500 USD",
    "",
    "LEG 1: Lahore -> Istanbul, Turkey",
    "  Departure date: 2026-09-10",
    "  Desired arrival time: before 18:00 local time",
    "  Stay: 4 nights (2026-09-10 to 2026-09-14)",
    "  Hotel budget: 110 USD per night, near Sultanahmet if possible",
    "",
    "LEG 2: Istanbul -> Paris, France",
    "  Departure date: 2026-09-14",
    "  Desired arrival time: before 15:00 local time",
    "  Stay: 3 nights (2026-09-14 to 2026-09-17)",
    "  Hotel budget: 150 USD per night",
    "",
    "RETURN: Paris -> Lahore",
    "  Departure date: 2026-09-17",
    "  Flexible on arrival time.",
    "",
    "Note: prefer at most 1 stop per flight; avoid overnight layovers.",
]


def esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


content_parts = ["BT /F1 11 Tf 72 740 Td 15 TL"]
for i, line in enumerate(TEXT_LINES):
    if i > 0:
        content_parts.append("T*")
    content_parts.append(f"({esc(line)}) Tj")
content_parts.append("ET")
content_stream = "\n".join(content_parts).encode("latin-1")

objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n"
    + content_stream + b"\nendstream",
]

out = bytearray(b"%PDF-1.4\n")
offsets = []
for i, obj in enumerate(objects, start=1):
    offsets.append(len(out))
    out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

xref_pos = len(out)
out += f"xref\n0 {len(objects) + 1}\n".encode()
out += b"0000000000 65535 f \n"
for off in offsets:
    out += f"{off:010d} 00000 n \n".encode()
out += (
    f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
    f"startxref\n{xref_pos}\n%%EOF\n"
).encode()

OUT.write_bytes(bytes(out))
print(f"Wrote {OUT} ({len(out)} bytes)")
