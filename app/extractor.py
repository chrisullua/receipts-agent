"""Agente de extracción: convierte una factura (PDF, imagen o texto) en datos estructurados.

Proveedores disponibles:
- "anthropic": usa Claude con tool use para obtener un JSON con esquema fijo.
- "mock": parser por reglas, sirve para probar el proyecto sin API key.
"""

import base64
import io
import re
from datetime import datetime
from decimal import Decimal

from app.config import Settings
from app.models import CATEGORIAS, FacturaExtraida

PROMPT_SISTEMA = """Sos un asistente contable argentino. Extraés los datos de facturas \
electrónicas emitidas según la normativa de ARCA (ex AFIP).
Reglas:
- El CUIT a extraer es el del EMISOR (proveedor), no el del cliente.
- Devolvé los importes como números, sin separador de miles y con punto decimal.
- Elegí la categoría de gasto más adecuada de la lista permitida.
- En "confianza" indicá de 0 a 1 qué tan seguro estás de los datos; bajala si el \
documento está borroso, incompleto o si tuviste que suponer algún dato."""

TOOL_FACTURA = {
    "name": "registrar_factura",
    "description": "Registra los datos extraídos de una factura.",
    "input_schema": {
        "type": "object",
        "properties": {
            "proveedor_nombre": {"type": "string"},
            "proveedor_cuit": {"type": "string", "description": "11 dígitos sin guiones"},
            "tipo_comprobante": {"type": "string", "enum": ["A", "B", "C"]},
            "punto_venta": {"type": "integer"},
            "numero": {"type": "integer"},
            "fecha_emision": {"type": "string", "description": "Formato YYYY-MM-DD"},
            "neto_gravado": {"type": "number"},
            "iva": {"type": "number"},
            "total": {"type": "number"},
            "moneda": {"type": "string", "description": "Código ISO, ej. ARS o USD"},
            "categoria": {"type": "string", "enum": CATEGORIAS},
            "confianza": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "proveedor_nombre", "proveedor_cuit", "tipo_comprobante", "punto_venta",
            "numero", "fecha_emision", "total", "categoria", "confianza",
        ],
    },
}

TIPOS_IMAGEN = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class ErrorExtraccion(Exception):
    pass


def texto_de_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader

    lector = PdfReader(io.BytesIO(contenido))
    return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)


def extraer(contenido: bytes, tipo_mime: str, settings: Settings) -> FacturaExtraida:
    if tipo_mime == "application/pdf":
        texto, imagen = texto_de_pdf(contenido), None
    elif tipo_mime in TIPOS_IMAGEN:
        texto, imagen = None, contenido
    elif tipo_mime.startswith("text/"):
        texto, imagen = contenido.decode("utf-8", errors="replace"), None
    else:
        raise ErrorExtraccion(f"Tipo de archivo no soportado: {tipo_mime}")

    if settings.llm_provider == "anthropic":
        return _extraer_con_claude(texto, imagen, tipo_mime, settings)
    if imagen is not None:
        raise ErrorExtraccion("El modo mock no lee imágenes; usá LLM_PROVIDER=anthropic.")
    return extraer_por_reglas(texto or "")


# ---------- Proveedor: Claude ----------

def _extraer_con_claude(texto, imagen, tipo_mime, settings: Settings) -> FacturaExtraida:
    import anthropic

    cliente = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    if imagen is not None:
        contenido = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": tipo_mime,
                    "data": base64.b64encode(imagen).decode(),
                },
            },
            {"type": "text", "text": "Extraé los datos de esta factura."},
        ]
    else:
        contenido = f"Extraé los datos de esta factura:\n\n{texto}"

    respuesta = cliente.messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=PROMPT_SISTEMA,
        tools=[TOOL_FACTURA],
        tool_choice={"type": "tool", "name": "registrar_factura"},
        messages=[{"role": "user", "content": contenido}],
    )
    for bloque in respuesta.content:
        if bloque.type == "tool_use":
            return FacturaExtraida.model_validate(bloque.input)
    raise ErrorExtraccion("El modelo no devolvió datos estructurados.")


# ---------- Proveedor: mock (reglas) ----------

PALABRAS_CATEGORIA = {
    "Tecnología": ["hosting", "software", "licencia", "notebook", "computadora", "internet"],
    "Insumos de oficina": ["resma", "papel", "toner", "librería", "lapicera"],
    "Servicios": ["luz", "energía", "gas", "agua", "limpieza", "telefonía"],
    "Alquiler": ["alquiler", "locación"],
    "Transporte": ["flete", "envío", "combustible", "nafta", "remis"],
    "Alimentos y bebidas": ["catering", "café", "almuerzo", "bebidas"],
    "Honorarios profesionales": ["honorarios", "asesoramiento", "consultoría"],
}


def _importe(texto: str, etiqueta: str) -> Decimal:
    m = re.search(etiqueta + r"[^\d\n]*([\d.]+,\d{2})", texto, re.IGNORECASE)
    if not m:
        return Decimal("0")
    return Decimal(m.group(1).replace(".", "").replace(",", "."))


def _buscar(patron: str, texto: str) -> str | None:
    m = re.search(patron, texto, re.IGNORECASE)
    return m.group(1).strip() if m else None


def extraer_por_reglas(texto: str) -> FacturaExtraida:
    nombre = _buscar(r"Raz[oó]n Social:\s*(.+)", texto)
    cuit = _buscar(r"CUIT:\s*([\d-]{11,13})", texto)
    tipo = _buscar(r"FACTURA\s+([ABC])\b", texto)
    pv = _buscar(r"Punto de Venta:\s*(\d+)", texto)
    nro = _buscar(r"Comp\.?\s*Nro:?\s*(\d+)", texto)
    fecha = _buscar(r"Fecha de Emisi[oó]n:\s*(\d{2}/\d{2}/\d{4})", texto)

    faltantes = [k for k, v in {"razón social": nombre, "CUIT": cuit, "tipo": tipo,
                                "punto de venta": pv, "número": nro, "fecha": fecha}.items() if not v]
    if faltantes:
        raise ErrorExtraccion("No se encontraron: " + ", ".join(faltantes))

    texto_min = texto.lower()
    categoria = next(
        (cat for cat, palabras in PALABRAS_CATEGORIA.items()
         if any(p in texto_min for p in palabras)),
        "Otros",
    )

    return FacturaExtraida(
        proveedor_nombre=nombre,
        proveedor_cuit=cuit,
        tipo_comprobante=tipo,
        punto_venta=int(pv),
        numero=int(nro),
        fecha_emision=datetime.strptime(fecha, "%d/%m/%Y").date(),
        neto_gravado=_importe(texto, r"Neto Gravado"),
        iva=_importe(texto, r"IVA\s*\d*[.,]?\d*%?"),
        total=_importe(texto, r"Importe Total"),
        moneda="USD" if "USD" in texto else "ARS",
        categoria=categoria,
        confianza=0.9,
    )
