"""Builds data/kb/aftercare-instructions.pdf, the PDF sample in the demo knowledge base."""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent.parent / "data" / "kb" / "aftercare-instructions.pdf"

SECTIONS = [
    ("After a tooth extraction", [
        "Bite on the gauze for 30 to 45 minutes after you leave. Replace it if it is soaked.",
        "Do not use a straw, spit, or smoke for 48 hours. These can loosen the blood clot.",
        "Use an ice pack on the cheek, 15 minutes on and 15 minutes off, for the first 24 hours.",
        "Eat soft, cool foods such as yogurt and soup for two days. Start gentle salt water rinses after 24 hours.",
        "Call us if bleeding continues for more than 4 hours, or if you have a fever or worsening pain after day three.",
    ]),
    ("After a filling", [
        "Your mouth stays numb for two to four hours. Do not chew until the numbness has gone, so you do not bite your cheek or tongue.",
        "Mild sensitivity to hot and cold is common for one to two weeks.",
        "Call us if your bite feels high or uneven after the numbness has gone.",
    ]),
    ("After teeth whitening", [
        "For the first 48 hours, avoid coffee, tea, red wine, tomato sauce and other dark foods and drinks. Stick to light-coloured foods.",
        "Sensitivity is normal for 24 to 48 hours. Use a toothpaste for sensitive teeth.",
        "Do not smoke during this period.",
    ]),
    ("After a root canal", [
        "You will have a temporary filling. Avoid chewing on that side until the permanent crown or filling is placed, usually within three weeks.",
        "Tenderness for a few days is normal and can be managed with over-the-counter pain relief.",
        "Call us if you have swelling, a visible bump on the gum, or pain that gets worse.",
    ]),
    ("After a crown is fitted", [
        "A temporary crown stays on for about two weeks. Avoid sticky foods such as caramel and gum.",
        "Floss by sliding the floss out sideways rather than pulling it up, so the temporary crown does not come off.",
        "If the temporary crown comes off, keep it and call us the same day.",
    ]),
]


def build() -> None:
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=22)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=16, spaceBefore=14)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=10.5, leading=14)

    story = [
        Paragraph("Aftercare Instructions", h1),
        Paragraph(
            "Maple Grove Dental. Follow these steps after your treatment. "
            "If something does not feel right, call the clinic. For urgent problems see the emergency guidance.",
            body,
        ),
        Spacer(1, 8),
    ]
    for title, items in SECTIONS:
        story.append(Paragraph(title, h2))
        story.append(
            ListFlowable([ListItem(Paragraph(i, body)) for i in items], bulletType="bullet", start="-")
        )
    SimpleDocTemplate(str(OUT), pagesize=letter, title="Aftercare Instructions",
                      author="Maple Grove Dental").build(story)


if __name__ == "__main__":
    build()
