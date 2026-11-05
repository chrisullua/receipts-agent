"""Informe mensual de gastos: texto plano y publicación en Google Docs."""

from decimal import Decimal

from app.config import Settings
from app.models import ResumenMensual

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def pesos(valor: Decimal) -> str:
    """Formato argentino: $ 1.234.567,89"""
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {texto}"


def titulo(resumen: ResumenMensual) -> str:
    return f"Informe de gastos - {MESES[resumen.mes - 1].capitalize()} {resumen.anio}"


def armar_texto(resumen: ResumenMensual) -> str:
    lineas = [
        titulo(resumen),
        "",
        f"Facturas procesadas: {resumen.cantidad_facturas}",
        f"Total del mes: {pesos(resumen.total_general)}",
        f"Pendientes de revisión: {resumen.pendientes_revision}",
        "",
        "Gasto por categoría:",
    ]
    for linea in resumen.lineas:
        porcentaje = (linea.total / resumen.total_general * 100) if resumen.total_general else 0
        porcentaje_txt = f"{porcentaje:.1f}".replace(".", ",")
        lineas.append(
            f"  - {linea.categoria}: {pesos(linea.total)} "
            f"({porcentaje_txt}%, {linea.cantidad} factura{'s' if linea.cantidad != 1 else ''})"
        )
    if resumen.pendientes_revision:
        lineas += ["", "Atención: hay facturas que necesitan revisión manual antes del cierre."]
    return "\n".join(lineas)


def publicar_en_google_docs(resumen: ResumenMensual, settings: Settings) -> str:
    """Crea un Google Doc con el informe y devuelve su URL."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    if not settings.google_credentials_file:
        raise RuntimeError("Falta configurar GOOGLE_CREDENTIALS_FILE.")

    credenciales = service_account.Credentials.from_service_account_file(
        settings.google_credentials_file,
        scopes=["https://www.googleapis.com/auth/documents",
                "https://www.googleapis.com/auth/drive.file"],
    )
    docs = build("docs", "v1", credentials=credenciales)
    documento = docs.documents().create(body={"title": titulo(resumen)}).execute()
    doc_id = documento["documentId"]

    texto = armar_texto(resumen)
    largo_titulo = len(titulo(resumen)) + 1
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [
            {"insertText": {"location": {"index": 1}, "text": texto}},
            {"updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": largo_titulo},
                "paragraphStyle": {"namedStyleType": "HEADING_1"},
                "fields": "namedStyleType",
            }},
        ]},
    ).execute()

    if settings.google_share_with:
        drive = build("drive", "v3", credentials=credenciales)
        drive.permissions().create(
            fileId=doc_id,
            body={"type": "user", "role": "writer", "emailAddress": settings.google_share_with},
        ).execute()

    return f"https://docs.google.com/document/d/{doc_id}/edit"
