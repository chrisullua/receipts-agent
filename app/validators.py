"""Reglas de negocio: el LLM extrae, pero el código valida.

Nada de lo que devuelve el modelo se guarda sin pasar por estas reglas.
"""

from decimal import Decimal

from app.models import CATEGORIAS, FacturaExtraida, FacturaProcesada

PESOS_CUIT = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
TOLERANCIA = Decimal("0.05")  # diferencia máxima aceptada por redondeos


def normalizar_cuit(cuit: str) -> str:
    return "".join(c for c in cuit if c.isdigit())


def cuit_valido(cuit: str) -> bool:
    """Valida el dígito verificador de un CUIT/CUIL argentino (algoritmo módulo 11)."""
    cuit = normalizar_cuit(cuit)
    if len(cuit) != 11:
        return False
    suma = sum(int(d) * p for d, p in zip(cuit[:10], PESOS_CUIT))
    verificador = 11 - (suma % 11)
    if verificador == 11:
        verificador = 0
    elif verificador == 10:
        return False
    return verificador == int(cuit[10])


def validar(factura: FacturaExtraida, umbral_confianza: float = 0.8) -> FacturaProcesada:
    observaciones: list[str] = []
    datos = factura.model_dump()
    datos["proveedor_cuit"] = normalizar_cuit(factura.proveedor_cuit)

    if not cuit_valido(datos["proveedor_cuit"]):
        observaciones.append("El CUIT del proveedor no es válido.")

    if factura.total <= 0:
        observaciones.append("El total debe ser mayor a cero.")

    # En facturas A el total debe ser neto + IVA (más otros tributos, que acá no se modelan)
    if factura.tipo_comprobante == "A":
        suma = factura.neto_gravado + factura.iva
        if abs(suma - factura.total) > TOLERANCIA:
            observaciones.append(
                f"Neto + IVA ({suma}) no coincide con el total ({factura.total})."
            )

    if factura.categoria not in CATEGORIAS:
        observaciones.append(f"Categoría desconocida '{factura.categoria}', se usa 'Otros'.")
        datos["categoria"] = "Otros"

    if factura.confianza < umbral_confianza:
        observaciones.append(f"Confianza baja en la extracción ({factura.confianza:.2f}).")

    return FacturaProcesada(
        **datos,
        requiere_revision=bool(observaciones),
        observaciones=observaciones,
    )
