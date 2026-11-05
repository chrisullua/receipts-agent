"""Acceso a datos. Hay dos implementaciones con la misma interfaz:

- PostgresRepository: la real, usada por la API.
- MemoryRepository: en memoria, usada por los tests (no necesita base de datos).
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.models import FacturaProcesada, LineaResumen, ResumenMensual


class FacturaDuplicada(Exception):
    pass


class Repository(Protocol):
    def guardar(self, factura: FacturaProcesada) -> FacturaProcesada: ...
    def listar(self, desde: date | None = None, hasta: date | None = None,
               solo_revision: bool = False) -> list[FacturaProcesada]: ...
    def resumen_mensual(self, anio: int, mes: int) -> ResumenMensual: ...


def _rango_mes(anio: int, mes: int) -> tuple[date, date]:
    inicio = date(anio, mes, 1)
    fin = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    return inicio, fin


def _armar_resumen(anio: int, mes: int, facturas: list[FacturaProcesada]) -> ResumenMensual:
    grupos: dict[str, list[FacturaProcesada]] = defaultdict(list)
    for f in facturas:
        grupos[f.categoria].append(f)
    lineas = [
        LineaResumen(
            categoria=cat,
            cantidad=len(fs),
            neto=sum((f.neto_gravado for f in fs), Decimal("0")),
            iva=sum((f.iva for f in fs), Decimal("0")),
            total=sum((f.total for f in fs), Decimal("0")),
        )
        for cat, fs in grupos.items()
    ]
    lineas.sort(key=lambda linea: linea.total, reverse=True)
    return ResumenMensual(
        anio=anio,
        mes=mes,
        lineas=lineas,
        total_general=sum((linea.total for linea in lineas), Decimal("0")),
        cantidad_facturas=len(facturas),
        pendientes_revision=sum(1 for f in facturas if f.requiere_revision),
    )


class MemoryRepository:
    def __init__(self):
        self._facturas: list[FacturaProcesada] = []

    def guardar(self, factura: FacturaProcesada) -> FacturaProcesada:
        clave = (factura.proveedor_cuit, factura.tipo_comprobante,
                 factura.punto_venta, factura.numero)
        for f in self._facturas:
            if (f.proveedor_cuit, f.tipo_comprobante, f.punto_venta, f.numero) == clave:
                raise FacturaDuplicada("La factura ya fue cargada.")
        guardada = factura.model_copy(update={"id": len(self._facturas) + 1})
        self._facturas.append(guardada)
        return guardada

    def listar(self, desde=None, hasta=None, solo_revision=False):
        return [
            f for f in self._facturas
            if (desde is None or f.fecha_emision >= desde)
            and (hasta is None or f.fecha_emision <= hasta)
            and (not solo_revision or f.requiere_revision)
        ]

    def resumen_mensual(self, anio, mes):
        inicio, fin = _rango_mes(anio, mes)
        facturas = [f for f in self._facturas if inicio <= f.fecha_emision < fin]
        return _armar_resumen(anio, mes, facturas)


class PostgresRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _conectar(self):
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.database_url, row_factory=dict_row)

    def guardar(self, factura: FacturaProcesada) -> FacturaProcesada:
        import psycopg

        with self._conectar() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO proveedores (cuit, razon_social) VALUES (%s, %s)
                   ON CONFLICT (cuit) DO UPDATE SET razon_social = EXCLUDED.razon_social
                   RETURNING id""",
                (factura.proveedor_cuit, factura.proveedor_nombre),
            )
            proveedor_id = cur.fetchone()["id"]
            cur.execute("SELECT id FROM categorias WHERE nombre = %s", (factura.categoria,))
            categoria_id = cur.fetchone()["id"]
            try:
                cur.execute(
                    """INSERT INTO facturas (proveedor_id, categoria_id, tipo_comprobante,
                           punto_venta, numero, fecha_emision, neto_gravado, iva, total,
                           moneda, confianza, requiere_revision, observaciones, archivo_origen)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (proveedor_id, categoria_id, factura.tipo_comprobante,
                     factura.punto_venta, factura.numero, factura.fecha_emision,
                     factura.neto_gravado, factura.iva, factura.total, factura.moneda,
                     factura.confianza, factura.requiere_revision,
                     "\n".join(factura.observaciones), factura.archivo_origen),
                )
            except psycopg.errors.UniqueViolation as e:
                raise FacturaDuplicada("La factura ya fue cargada.") from e
            return factura.model_copy(update={"id": cur.fetchone()["id"]})

    def listar(self, desde=None, hasta=None, solo_revision=False):
        condiciones, params = [], []
        if desde:
            condiciones.append("f.fecha_emision >= %s")
            params.append(desde)
        if hasta:
            condiciones.append("f.fecha_emision <= %s")
            params.append(hasta)
        if solo_revision:
            condiciones.append("f.requiere_revision")
        where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
        with self._conectar() as conn, conn.cursor() as cur:
            cur.execute(
                f"""SELECT f.*, p.cuit AS proveedor_cuit, p.razon_social AS proveedor_nombre,
                           c.nombre AS categoria
                    FROM facturas f
                    JOIN proveedores p ON p.id = f.proveedor_id
                    JOIN categorias c ON c.id = f.categoria_id
                    {where}
                    ORDER BY f.fecha_emision DESC""",
                params,
            )
            filas = cur.fetchall()
        return [
            FacturaProcesada(
                **{**fila, "confianza": float(fila["confianza"] or 0),
                   "observaciones": [o for o in (fila["observaciones"] or "").split("\n") if o]}
            )
            for fila in filas
        ]

    def resumen_mensual(self, anio, mes):
        inicio, fin = _rango_mes(anio, mes)
        facturas = [f for f in self.listar(desde=inicio) if f.fecha_emision < fin]
        return _armar_resumen(anio, mes, facturas)
