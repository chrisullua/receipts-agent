"""API REST del Agente de Facturas y Gastos."""

from datetime import date

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from app import report
from app.config import Settings, get_settings
from app.extractor import ErrorExtraccion, extraer
from app.models import FacturaProcesada, ResumenMensual
from app.repository import FacturaDuplicada, PostgresRepository, Repository
from app.validators import validar

app = FastAPI(
    title="Agente de Facturas y Gastos",
    description="Extrae datos de facturas con IA, los valida y genera informes mensuales.",
    version="1.0.0",
)

MAX_BYTES = 10 * 1024 * 1024


def get_repo(settings: Settings = Depends(get_settings)) -> Repository:
    return PostgresRepository(settings.database_url)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/facturas", response_model=FacturaProcesada, status_code=201)
async def cargar_factura(
    archivo: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    repo: Repository = Depends(get_repo),
):
    """Recibe una factura (PDF, imagen o texto), extrae sus datos, los valida y los guarda."""
    contenido = await archivo.read()
    if len(contenido) > MAX_BYTES:
        raise HTTPException(413, "El archivo supera los 10 MB.")

    try:
        extraida = extraer(contenido, archivo.content_type or "", settings)
    except ErrorExtraccion as e:
        raise HTTPException(422, str(e))

    factura = validar(extraida, settings.umbral_confianza)
    factura.archivo_origen = archivo.filename
    try:
        return repo.guardar(factura)
    except FacturaDuplicada as e:
        raise HTTPException(409, str(e))


@app.get("/facturas", response_model=list[FacturaProcesada])
def listar_facturas(
    desde: date | None = None,
    hasta: date | None = None,
    solo_revision: bool = False,
    repo: Repository = Depends(get_repo),
):
    return repo.listar(desde, hasta, solo_revision)


@app.get("/informes/{anio}/{mes}", response_model=ResumenMensual)
def informe_mensual(anio: int, mes: int, repo: Repository = Depends(get_repo)):
    if not 1 <= mes <= 12:
        raise HTTPException(400, "El mes debe estar entre 1 y 12.")
    return repo.resumen_mensual(anio, mes)


@app.get("/informes/{anio}/{mes}/texto", response_class=PlainTextResponse)
def informe_mensual_texto(anio: int, mes: int, repo: Repository = Depends(get_repo)):
    return report.armar_texto(informe_mensual(anio, mes, repo))


@app.post("/informes/{anio}/{mes}/google-docs")
def publicar_informe(
    anio: int,
    mes: int,
    settings: Settings = Depends(get_settings),
    repo: Repository = Depends(get_repo),
):
    resumen = informe_mensual(anio, mes, repo)
    try:
        url = report.publicar_en_google_docs(resumen, settings)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {"url": url}
