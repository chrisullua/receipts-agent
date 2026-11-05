-- Esquema de la base de datos del Agente de Facturas y Gastos
-- Se ejecuta automáticamente al levantar el contenedor de PostgreSQL.

CREATE TABLE IF NOT EXISTS proveedores (
    id           SERIAL PRIMARY KEY,
    cuit         VARCHAR(11) UNIQUE NOT NULL,
    razon_social VARCHAR(200) NOT NULL,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS categorias (
    id     SERIAL PRIMARY KEY,
    nombre VARCHAR(50) UNIQUE NOT NULL
);

INSERT INTO categorias (nombre) VALUES
    ('Servicios'), ('Insumos de oficina'), ('Tecnología'), ('Alquiler'),
    ('Transporte'), ('Alimentos y bebidas'), ('Honorarios profesionales'),
    ('Impuestos y tasas'), ('Otros')
ON CONFLICT (nombre) DO NOTHING;

CREATE TABLE IF NOT EXISTS facturas (
    id                SERIAL PRIMARY KEY,
    proveedor_id      INTEGER NOT NULL REFERENCES proveedores(id),
    categoria_id      INTEGER NOT NULL REFERENCES categorias(id),
    tipo_comprobante  CHAR(1) NOT NULL CHECK (tipo_comprobante IN ('A', 'B', 'C')),
    punto_venta       INTEGER NOT NULL,
    numero            INTEGER NOT NULL,
    fecha_emision     DATE NOT NULL,
    neto_gravado      NUMERIC(14, 2) NOT NULL DEFAULT 0,
    iva               NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total             NUMERIC(14, 2) NOT NULL,
    moneda            CHAR(3) NOT NULL DEFAULT 'ARS',
    confianza         NUMERIC(3, 2),             -- confianza de la extracción (0 a 1)
    requiere_revision BOOLEAN NOT NULL DEFAULT false,
    observaciones     TEXT,
    archivo_origen    VARCHAR(255),
    creado_en         TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Evita cargar dos veces la misma factura
    CONSTRAINT factura_unica UNIQUE (proveedor_id, tipo_comprobante, punto_venta, numero)
);

CREATE INDEX IF NOT EXISTS idx_facturas_fecha ON facturas (fecha_emision);

-- Vista para el informe mensual
CREATE OR REPLACE VIEW resumen_mensual AS
SELECT
    date_trunc('month', f.fecha_emision)::date AS mes,
    c.nombre                                   AS categoria,
    COUNT(*)                                   AS cantidad,
    SUM(f.neto_gravado)                        AS neto,
    SUM(f.iva)                                 AS iva,
    SUM(f.total)                               AS total
FROM facturas f
JOIN categorias c ON c.id = f.categoria_id
GROUP BY 1, 2;
