import logging
"""
Service d'export PDF — Rapport mensuel Foyio.
Utilise reportlab pour générer un PDF mis en page.
"""
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
logger = logging.getLogger(__name__)

# ── Palette gris Foyio ──
C_DARK   = colors.HexColor("#1e2124")
C_MID    = colors.HexColor("#292d32")
C_BORDER = colors.HexColor("#3d4248")
C_TEXT   = colors.HexColor("#c8cdd4")
C_MUTED  = colors.HexColor("#848c94")
C_GREEN  = colors.HexColor("#22c55e")
C_RED    = colors.HexColor("#ef4444")
C_WHITE  = colors.HexColor("#ffffff")

def _styles():
    return {
        "title": ParagraphStyle(
            "title", fontName="Helvetica-Bold", fontSize=22,
            textColor=C_DARK, spaceAfter=16, spaceBefore=8, alignment=TA_LEFT
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName="Helvetica", fontSize=11,
            textColor=C_MUTED, spaceAfter=16, alignment=TA_LEFT
        ),
        "section": ParagraphStyle(
            "section", fontName="Helvetica-Bold", fontSize=12,
            textColor=C_DARK, spaceBefore=14, spaceAfter=6, alignment=TA_LEFT
        ),
        "normal": ParagraphStyle(
            "normal", fontName="Helvetica", fontSize=9,
            textColor=C_DARK, alignment=TA_LEFT
        ),
        "amount_pos": ParagraphStyle(
            "amount_pos", fontName="Helvetica-Bold", fontSize=9,
            textColor=C_GREEN, alignment=TA_RIGHT
        ),
        "amount_neg": ParagraphStyle(
            "amount_neg", fontName="Helvetica-Bold", fontSize=9,
            textColor=C_RED, alignment=TA_RIGHT
        ),
        "amount_neu": ParagraphStyle(
            "amount_neu", fontName="Helvetica-Bold", fontSize=9,
            textColor=C_DARK, alignment=TA_RIGHT
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label", fontName="Helvetica", fontSize=9,
            textColor=C_MUTED, alignment=TA_CENTER
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value", fontName="Helvetica-Bold", fontSize=16,
            textColor=C_DARK, alignment=TA_CENTER
        ),
    }


def export_pdf(filepath: str, year: int, month: int, account_id=None) -> int:
    """
    Génère le rapport PDF mensuel.
    Retourne le nombre de transactions exportées.
    """
    from db import Session
    from models import Transaction, Category
    from sqlalchemy import func
    from utils.formatters import format_money
    import account_state

    if account_id is None:
        account_id = account_state.get_id()

    MONTHS_FR = ["", "Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre"]

    period_label = f"{MONTHS_FR[month]} {year}"

    # Récupérer les données
    with Session() as session:
        q = (session.query(Transaction)
             .filter(func.extract("year",  Transaction.date) == year)
             .filter(func.extract("month", Transaction.date) == month))
        if account_id:
            q = q.filter(Transaction.account_id == account_id)
        transactions = q.order_by(Transaction.date.desc()).all()

        cats = {c.id: c.name for c in session.query(Category).all()}
        session.expunge_all()

    income  = sum(t.amount for t in transactions if t.type == "income")
    expense = sum(t.amount for t in transactions if t.type == "expense")
    balance = income - expense

    # ── Création du document ──
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    S = _styles()
    story = []

    # ── En-tête ──
    story.append(Paragraph("Foyio", S["title"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Rapport mensuel — {period_label} — "
        f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        S["subtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=C_BORDER, spaceAfter=14))

    # ── KPIs ──
    story.append(Paragraph("Synthèse", S["section"]))

    bal_color = C_GREEN if balance >= 0 else C_RED
    bal_style = ParagraphStyle("bal", fontName="Helvetica-Bold", fontSize=16,
                               textColor=bal_color, alignment=TA_CENTER)
    sign = "+" if balance >= 0 else "-"

    kpi_data = [[
        Paragraph("Revenus",           S["kpi_label"]),
        Paragraph("Dépenses",          S["kpi_label"]),
        Paragraph("Solde",             S["kpi_label"]),
    ], [
        Paragraph(f"+{format_money(income)}",        S["kpi_value"]),
        Paragraph(f"-{format_money(expense)}",       ParagraphStyle(
            "kpi_neg", fontName="Helvetica-Bold", fontSize=16,
            textColor=C_RED, alignment=TA_CENTER
        )),
        Paragraph(f"{sign}{format_money(abs(balance))}", bal_style),
    ]]

    kpi_table = Table(kpi_data, colWidths=["33%", "33%", "34%"])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ("BOX",        (0, 0), (-1, -1), 0.5, C_BORDER),
        ("INNERGRID",  (0, 0), (-1, -1), 0.5, C_BORDER),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 0), (-1, 0), [colors.HexColor("#f1f3f4")]),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    # ── Tableau des transactions ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8))
    story.append(Paragraph("Détail des transactions", S["section"]))

    if not transactions:
        story.append(Paragraph("Aucune transaction ce mois.", S["normal"]))
    else:
        headers = ["Date", "Type", "Catégorie", "Description", "Montant"]
        rows = [headers]

        for t in transactions:
            cat_name = cats.get(t.category_id, "—")
            ttype    = "Revenu" if t.type == "income" else "Dépense"
            sign_tx  = "+" if t.type == "income" else "-"
            color_tx = C_GREEN if t.type == "income" else C_RED
            amt_style = ParagraphStyle(
                "amt", fontName="Helvetica-Bold", fontSize=9,
                textColor=color_tx, alignment=TA_RIGHT
            )
            rows.append([
                Paragraph(t.date.strftime("%d/%m/%Y"), S["normal"]),
                Paragraph(ttype,                        S["normal"]),
                Paragraph(cat_name[:22],                S["normal"]),
                Paragraph((t.note or "—")[:35],         S["normal"]),
                Paragraph(f"{sign_tx}{format_money(t.amount)}", amt_style),
            ])

        col_w = [2.2*cm, 2*cm, 3.5*cm, 8*cm, 2.8*cm]
        tx_table = Table(rows, colWidths=col_w, repeatRows=1)
        tx_table.setStyle(TableStyle([
            # En-tête
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2e3238")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
            ("TOPPADDING",    (0, 0), (-1, 0), 7),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
            # Lignes
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, -1), 9),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 1), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1),
             [colors.HexColor("#ffffff"), colors.HexColor("#f8f9fa")]),
            ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
            ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        story.append(tx_table)

    story.append(Spacer(1, 14))

    # ── Dépenses par catégorie ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8))
    story.append(Paragraph("Dépenses par catégorie", S["section"]))

    exp_by_cat = {}
    for t in transactions:
        if t.type == "expense":
            cat = cats.get(t.category_id, "Autre")
            exp_by_cat[cat] = exp_by_cat.get(cat, 0) + t.amount

    if exp_by_cat:
        cat_rows = [["Catégorie", "Montant", "%"]]
        for cat, amt in sorted(exp_by_cat.items(), key=lambda x: -x[1]):
            pct = amt / expense * 100 if expense > 0 else 0
            cat_rows.append([
                Paragraph(cat, S["normal"]),
                Paragraph(format_money(amt), ParagraphStyle(
                    "r", fontName="Helvetica", fontSize=9,
                    textColor=C_RED, alignment=TA_RIGHT)),
                Paragraph(f"{pct:.1f}%", ParagraphStyle(
                    "p", fontName="Helvetica", fontSize=9,
                    textColor=C_MUTED, alignment=TA_RIGHT)),
            ])
        cat_table = Table(cat_rows, colWidths=["60%", "25%", "15%"])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2e3238")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1),
             [colors.HexColor("#ffffff"), colors.HexColor("#f8f9fa")]),
            ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
            ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        story.append(cat_table)

    story.append(Spacer(1, 14))

    # ── Objectifs épargne ──
    try:
        from services.savings_service import get_goals
        goals = get_goals()
        if goals:
            story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8))
            story.append(Paragraph("Objectifs d'epargne", S["section"]))
            sav_rows = [["Objectif", "Epargné", "Cible", "Progression"]]
            for g in goals:
                pct = g.current_amount / g.target_amount * 100 if g.target_amount > 0 else 0
                sav_rows.append([
                    Paragraph(g.name, S["normal"]),
                    Paragraph(format_money(g.current_amount), ParagraphStyle(
                        "gv", fontName="Helvetica", fontSize=9,
                        textColor=C_GREEN, alignment=TA_RIGHT)),
                    Paragraph(format_money(g.target_amount), ParagraphStyle(
                        "gt", fontName="Helvetica", fontSize=9,
                        textColor=C_MUTED, alignment=TA_RIGHT)),
                    Paragraph(f"{pct:.0f}%", ParagraphStyle(
                        "gp", fontName="Helvetica-Bold", fontSize=9,
                        textColor=C_GREEN if pct >= 100 else C_MUTED, alignment=TA_CENTER)),
                ])
            sav_table = Table(sav_rows, colWidths=["40%", "20%", "20%", "20%"])
            sav_table.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2e3238")),
                ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE",      (0, 0), (-1, 0), 9),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1),
                 [colors.HexColor("#ffffff"), colors.HexColor("#f8f9fa")]),
                ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
                ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ]))
            story.append(sav_table)
    except Exception:
        logger.warning("Exception silencieuse", exc_info=True)
    # ── Pied de page ──
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6))
    story.append(Paragraph("Foyio — Gestion financiere personnelle — " + (__import__("services.settings_service", fromlist=["get"]).get("user_name") or "Foyio"),
        ParagraphStyle("footer", fontName="Helvetica", fontSize=8,
        textColor=C_MUTED, alignment=TA_CENTER)))

    doc.build(story)
    return len(transactions)
