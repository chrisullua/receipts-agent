from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

CATEGORIAS = [
    "Servicios",
    "Insumos de oficina",
    "Tecnología",
    "Alquiler",
    "Transporte",
    "Alimentos y bebidas",
    "Honorarios profesionales",
    "Impuestos y tasas",
    "Otros",
]


class FacturaExtraida(BaseModel):
    """Datos que el agente extrae de una factura."""

    proveedor_nombre: str
    proveedor_cuit: str = Field(description="11 dígitos, sin guiones")
    tipo_comprobante: Literal["A", "B", "C"]
    punto_venta: int
    numero: int
    fecha_emision: date
    neto_gravado: Decimal = Decimal("0")
    iva: Decimal = Decimal("0")
    total: Decimal
    moneda: str = "ARS"
    categoria: str = "Otros"
    confianza: float = Field(ge=0, le=1, default=1.0)


class FacturaProcesada(FacturaExtraida):
    """Factura ya validada, lista para guardar o devolver por la API."""

    id: int | None = None
    requiere_revision: bool = False
    observaciones: list[str] = []
    archivo_origen: str | None = None


class LineaResumen(BaseModel):
    categoria: str
    cantidad: int
    neto: Decimal
    iva: Decimal
    total: Decimal


class ResumenMensual(BaseModel):
    anio: int
    mes: int
    lineas: list[LineaResumen]
    total_general: Decimal
    cantidad_facturas: int
    pendientes_revision: int
