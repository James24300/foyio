"""
Service de rapport fiscal annuel — Foyio.
Génère les données et le PDF du rapport fiscal annuel.
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_fiscal_report(year, account_id=None):
    """
    Génère un rapport fiscal annuel.
    Retourne un dict avec :
      - total_income, total_expense, net_balance
      - monthly_breakdown : liste de 12 dicts {month, income, expense, balance}
      - category_totals : dict catégorie -> {income, expense} trié par dépense desc.
      - top_expenses : top 10 plus grosses dépenses
    """
    from db import Session
    from models import Transaction, Category
    from sqlalchemy import func
    import account_state

    if account_id is None:
        account_id = account_state.get_id()

    with Session() as session:
        q = (session.query(Transaction)
             .filter(func.extract("year", Transaction.date) == year))
        if account_id:
            q = q.filter(Transaction.account_id == account_id)
        transactions = q.order_by(Transaction.date.desc()).all()

        cats = {c.id: c.name for c in session.query(Category).all()}
        session.expunge_all()

    # ── Totaux ──
    total_income  = sum(t.amount for t in transactions if t.type == "income")
    total_expense = sum(t.amount for t in transactions if t.type == "expense")
    net_balance   = total_income - total_expense

    # ── Ventilation mensuelle ──
    MONTHS_FR = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

    monthly_breakdown = []
    for m in range(1, 13):
        m_income  = sum(t.amount for t in transactions
                        if t.type == "income" and t.date.month == m)
        m_expense = sum(t.amount for t in transactions
                        if t.type == "expense" and t.date.month == m)
        monthly_breakdown.append({
            "month":   MONTHS_FR[m],
            "income":  m_income,
            "expense": m_expense,
            "balance": m_income - m_expense,
        })

    # ── Totaux par catégorie ──
    cat_data = {}
    for t in transactions:
        cat_name = cats.get(t.category_id, "Autre")
        if cat_name not in cat_data:
            cat_data[cat_name] = {"income": 0, "expense": 0}
        if t.type == "income":
            cat_data[cat_name]["income"] += t.amount
        else:
            cat_data[cat_name]["expense"] += t.amount

    # Trier par dépense décroissante
    category_totals = dict(
        sorted(cat_data.items(), key=lambda x: -x[1]["expense"])
    )

    # ── Top 10 dépenses ──
    expenses_sorted = sorted(
        [t for t in transactions if t.type == "expense"],
        key=lambda t: -t.amount
    )[:10]
    top_expenses = []
    for t in expenses_sorted:
        top_expenses.append({
            "date":        t.date.strftime("%d/%m/%Y"),
            "description": t.note or "—",
            "amount":      t.amount,
            "category":    cats.get(t.category_id, "Autre"),
        })

    return {
        "total_income":      total_income,
        "total_expense":     total_expense,
        "net_balance":       net_balance,
        "monthly_breakdown": monthly_breakdown,
        "category_totals":   category_totals,
        "top_expenses":      top_expenses,
    }


# ── Export PDF ──────────────────────────────────────────────────────────

def export_fiscal_pdf(year, account_id=None, filepath=None):
    """
    Génère un PDF de rapport fiscal annuel.
    Retourne le chemin du fichier créé.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from utils.formatters import format_money

    # Chemin par défaut = Bureau
    if filepath is None:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        filepath = os.path.join(desktop, f"rapport_fiscal_{year}.pdf")

    # ── Palette Foyio ──
    C_DARK   = colors.HexColor("#1e2124")
    C_BORDER = colors.HexColor("#3d4248")
    C_MUTED  = colors.HexColor("#848c94")
    C_GREEN  = colors.HexColor("#22c55e")
    C_RED    = colors.HexColor("#ef4444")
    C_WHITE  = colors.HexColor("#ffffff")

    # ── Styles ──
    S = {
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
        "kpi_label": ParagraphStyle(
            "kpi_label", fontName="Helvetica", fontSize=9,
            textColor=C_MUTED, alignment=TA_CENTER
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value", fontName="Helvetica-Bold", fontSize=16,
            textColor=C_DARK, alignment=TA_CENTER
        ),
    }

    # ── Données ──
    data = generate_fiscal_report(year, account_id)

    # ── Document ──
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )
    story = []

    # ── En-tête ──
    story.append(Paragraph(f"Rapport Fiscal {year} — Foyio", S["title"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        S["subtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=C_BORDER, spaceAfter=14))

    # ── Synthèse (KPIs) ──
    story.append(Paragraph("Synthèse annuelle", S["section"]))

    bal = data["net_balance"]
    bal_color = C_GREEN if bal >= 0 else C_RED
    bal_style = ParagraphStyle("bal", fontName="Helvetica-Bold", fontSize=16,
                               textColor=bal_color, alignment=TA_CENTER)
    sign = "+" if bal >= 0 else "-"

    kpi_data = [[
        Paragraph("Revenus totaux",  S["kpi_label"]),
        Paragraph("Dépenses totales", S["kpi_label"]),
        Paragraph("Solde net",       S["kpi_label"]),
    ], [
        Paragraph(f"+{format_money(data['total_income'])}", S["kpi_value"]),
        Paragraph(f"-{format_money(data['total_expense'])}", ParagraphStyle(
            "kpi_neg", fontName="Helvetica-Bold", fontSize=16,
            textColor=C_RED, alignment=TA_CENTER
        )),
        Paragraph(f"{sign}{format_money(abs(bal))}", bal_style),
    ]]

    kpi_table = Table(kpi_data, colWidths=["33%", "33%", "34%"])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, C_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 0), (-1, 0), [colors.HexColor("#f1f3f4")]),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    # ── Tableau mensuel ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8))
    story.append(Paragraph("Ventilation mensuelle", S["section"]))

    month_rows = [["Mois", "Revenus", "Dépenses", "Solde"]]
    for m in data["monthly_breakdown"]:
        m_bal = m["balance"]
        m_color = C_GREEN if m_bal >= 0 else C_RED
        month_rows.append([
            Paragraph(m["month"], S["normal"]),
            Paragraph(f"+{format_money(m['income'])}", ParagraphStyle(
                "mg", fontName="Helvetica", fontSize=9,
                textColor=C_GREEN, alignment=TA_RIGHT)),
            Paragraph(f"-{format_money(m['expense'])}", ParagraphStyle(
                "mr", fontName="Helvetica", fontSize=9,
                textColor=C_RED, alignment=TA_RIGHT)),
            Paragraph(f"{'+' if m_bal >= 0 else '-'}{format_money(abs(m_bal))}",
                      ParagraphStyle(
                          "mb", fontName="Helvetica-Bold", fontSize=9,
                          textColor=m_color, alignment=TA_RIGHT)),
        ])

    month_table = Table(month_rows, colWidths=["30%", "23%", "23%", "24%"])
    month_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2e3238")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 9),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.HexColor("#ffffff"), colors.HexColor("#f8f9fa")]),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
    ]))
    story.append(month_table)
    story.append(Spacer(1, 14))

    # ── Dépenses par catégorie ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8))
    story.append(Paragraph("Dépenses par catégorie", S["section"]))

    total_exp = data["total_expense"]
    cat_rows = [["Catégorie", "Montant dépensé", "% du total"]]
    for cat_name, vals in data["category_totals"].items():
        if vals["expense"] > 0:
            pct = vals["expense"] / total_exp * 100 if total_exp > 0 else 0
            cat_rows.append([
                Paragraph(cat_name, S["normal"]),
                Paragraph(format_money(vals["expense"]), ParagraphStyle(
                    "cr", fontName="Helvetica", fontSize=9,
                    textColor=C_RED, alignment=TA_RIGHT)),
                Paragraph(f"{pct:.1f}%", ParagraphStyle(
                    "cp", fontName="Helvetica", fontSize=9,
                    textColor=C_MUTED, alignment=TA_RIGHT)),
            ])

    if len(cat_rows) > 1:
        cat_table = Table(cat_rows, colWidths=["50%", "30%", "20%"])
        cat_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2e3238")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#ffffff"), colors.HexColor("#f8f9fa")]),
            ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
            ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        story.append(cat_table)
    else:
        story.append(Paragraph("Aucune dépense enregistrée.", S["normal"]))

    story.append(Spacer(1, 14))

    # ── Top 10 dépenses ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=8))
    story.append(Paragraph("Top 10 dépenses", S["section"]))

    if data["top_expenses"]:
        top_rows = [["Date", "Description", "Montant", "Catégorie"]]
        for exp in data["top_expenses"]:
            top_rows.append([
                Paragraph(exp["date"], S["normal"]),
                Paragraph(exp["description"][:35], S["normal"]),
                Paragraph(f"-{format_money(exp['amount'])}", ParagraphStyle(
                    "tr", fontName="Helvetica-Bold", fontSize=9,
                    textColor=C_RED, alignment=TA_RIGHT)),
                Paragraph(exp["category"][:22], S["normal"]),
            ])

        top_table = Table(top_rows, colWidths=[2.2*cm, 8*cm, 3*cm, 3.5*cm])
        top_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#2e3238")),
            ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 9),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.HexColor("#ffffff"), colors.HexColor("#f8f9fa")]),
            ("BOX",           (0, 0), (-1, -1), 0.5, C_BORDER),
            ("INNERGRID",     (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        story.append(top_table)
    else:
        story.append(Paragraph("Aucune dépense enregistrée.", S["normal"]))

    # ── Pied de page ──
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER, spaceAfter=6))
    story.append(Paragraph(
        "Foyio — Rapport fiscal annuel — " +
        (__import__("services.settings_service", fromlist=["get"]).get("user_name") or "Foyio"),
        ParagraphStyle("footer", fontName="Helvetica", fontSize=8,
                       textColor=C_MUTED, alignment=TA_CENTER)
    ))

    doc.build(story)
    logger.info("Rapport fiscal %d exporté : %s", year, filepath)
    return filepath
