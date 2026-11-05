from datetime import date
from decimal import Decimal

from app.models import FacturaExtraida
from app.validators import cuit_valido, validar


def factura(**cambios):
    base = dict(
        proveedor_nombre="Proveedor S.A.", proveedor_cuit="30-71234567-1",
        tipo_comprobante="A", punto_venta=1, numero=10, fecha_emision=date(2026, 10, 1),
        neto_gravado=Decimal("100"), iva=Decimal("21"), total=Decimal("121"),
        categoria="Servicios", confianza=0.95,
    )
    return FacturaExtraida(**{**base, **cambios})


def test_cuit_valido():
    assert cuit_valido("30-71234567-1")
    assert cuit_valido("20345678906")


def test_cuit_invalido():
    assert not cuit_valido("30-71234567-2")  # dígito verificador incorrecto
    assert not cuit_valido("123")            # largo incorrecto


def test_factura_correcta_no_requiere_revision():
    resultado = validar(factura())
    assert not resultado.requiere_revision
    assert resultado.proveedor_cuit == "30712345671"


def test_factura_a_con_totales_que_no_cierran():
    resultado = validar(factura(total=Decimal("130")))
    assert resultado.requiere_revision
    assert any("no coincide" in o for o in resultado.observaciones)


def test_factura_b_no_exige_discriminar_iva():
    resultado = validar(factura(tipo_comprobante="B", neto_gravado=0, iva=0))
    assert not resultado.requiere_revision


def test_confianza_baja_pide_revision():
    resultado = validar(factura(confianza=0.5), umbral_confianza=0.8)
    assert resultado.requiere_revision


def test_categoria_desconocida_pasa_a_otros():
    resultado = validar(factura(categoria="Viajes espaciales"))
    assert resultado.categoria == "Otros"
