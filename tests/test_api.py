from decimal import Decimal

from app.extractor import extraer_por_reglas
from app.report import armar_texto, pesos
from tests.conftest import SAMPLES, subir


def test_extraccion_por_reglas_factura_a():
    f = extraer_por_reglas((SAMPLES / "factura_a_hosting.txt").read_text())
    assert f.proveedor_nombre == "Nube Atlántica S.A."
    assert f.tipo_comprobante == "A"
    assert (f.punto_venta, f.numero) == (3, 1234)
    assert f.total == Decimal("102850.00")
    assert f.iva == Decimal("17850.00")
    assert f.categoria == "Tecnología"


def test_cargar_factura(client):
    r = subir(client, "factura_a_hosting.txt")
    assert r.status_code == 201
    datos = r.json()
    assert datos["id"] == 1
    assert datos["requiere_revision"] is False


def test_factura_duplicada_devuelve_409(client):
    subir(client, "factura_c_honorarios.txt")
    r = subir(client, "factura_c_honorarios.txt")
    assert r.status_code == 409


def test_factura_con_errores_queda_para_revision(client):
    r = subir(client, "factura_a_con_errores.txt")
    assert r.status_code == 201
    datos = r.json()
    assert datos["requiere_revision"] is True
    assert len(datos["observaciones"]) == 2  # CUIT inválido y totales que no cierran

    pendientes = client.get("/facturas", params={"solo_revision": True}).json()
    assert len(pendientes) == 1


def test_archivo_no_soportado(client):
    r = client.post("/facturas", files={"archivo": ("x.zip", b"123", "application/zip")})
    assert r.status_code == 422


def test_informe_mensual(client):
    for nombre in ["factura_a_hosting.txt", "factura_b_libreria.txt",
                   "factura_c_honorarios.txt", "factura_a_con_errores.txt"]:
        subir(client, nombre)

    r = client.get("/informes/2026/10")
    assert r.status_code == 200
    resumen = r.json()
    assert resumen["cantidad_facturas"] == 4
    assert Decimal(resumen["total_general"]) == Decimal("367300.00")
    assert resumen["pendientes_revision"] == 1
    assert resumen["lineas"][0]["categoria"] == "Honorarios profesionales"

    texto = client.get("/informes/2026/10/texto").text
    assert "Octubre 2026" in texto


def test_formato_pesos():
    assert pesos(Decimal("1234567.5")) == "$ 1.234.567,50"
