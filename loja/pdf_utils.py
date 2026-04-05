from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def gerar_pdf_venda(venda):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "titulo",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#C2185B"),
    )

    elementos = [
        Paragraph("Bela e Cheirosa Multimarcas", titulo),
        Paragraph("Comprovante de Venda", styles["Normal"]),
        Spacer(1, 0.4 * cm),
    ]

    cliente_nome = venda.cliente.nome if venda.cliente else "Consumidor Final"
    info = [
        ["Venda", f"#{venda.id:05d}"],
        ["Data", venda.data.strftime("%d/%m/%Y %H:%M")],
        ["Cliente", cliente_nome],
        ["Pagamento", venda.get_forma_pagamento_display()],
        ["Status", venda.get_status_display()],
    ]
    t_info = Table(info, colWidths=[4 * cm, 10 * cm])
    t_info.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.extend([t_info, Spacer(1, 0.4 * cm)])

    itens = [["Produto", "Qtd", "Preço", "Subtotal"]]
    for item in venda.itens.all():
        itens.append([
            item.produto.nome,
            str(item.quantidade),
            f"R$ {item.preco_unitario:.2f}",
            f"R$ {item.subtotal:.2f}",
        ])

    t_itens = Table(itens, colWidths=[8 * cm, 2 * cm, 3 * cm, 3 * cm])
    t_itens.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C2185B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E0E0")),
    ]))
    elementos.extend([t_itens, Spacer(1, 0.3 * cm)])

    totais = [
        ["Subtotal", f"R$ {venda.subtotal:.2f}"],
        ["Desconto", f"R$ {venda.desconto:.2f}"],
        ["TOTAL", f"R$ {venda.total:.2f}"],
    ]
    t_totais = Table(totais, colWidths=[10 * cm, 4 * cm])
    t_totais.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.HexColor("#C2185B")),
    ]))
    elementos.append(t_totais)

    doc.build(elementos)
    buffer.seek(0)
    return buffer
