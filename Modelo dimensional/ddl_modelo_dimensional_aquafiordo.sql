-- =====================================================================
-- MODELO DIMENSIONAL - AQUAFIORDO
-- Constelación de 4 hechos con dimensiones conformadas
-- Dialecto: ANSI SQL / PostgreSQL (usar SERIAL o IDENTITY según motor)
-- =====================================================================

-- =====================================================================
-- 1. DIMENSIONES CONFORMADAS
-- =====================================================================

-- ---------------------------------------------------------------------
-- Dim_Tiempo: grano día. Se referencia con distintos "roles" desde los
-- hechos (fecha de operación, fecha de cosecha, fecha inicio/fin de
-- evento sanitario, mes de vigencia del precio de alimento).
-- ---------------------------------------------------------------------
CREATE TABLE dim_tiempo (
    tiempo_id       INTEGER PRIMARY KEY,        -- surrogate, formato YYYYMMDD
    fecha           DATE NOT NULL,
    dia             SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    nombre_mes      VARCHAR(15) NOT NULL,
    trimestre       SMALLINT NOT NULL,
    anio            SMALLINT NOT NULL,
    dia_semana      VARCHAR(10) NOT NULL,
    es_habil        BOOLEAN NOT NULL,
    anio_mes        CHAR(7) NOT NULL,            -- 'YYYY-MM', para el grano de Dim_Alimento/Hecho_CostoAlimento
    UNIQUE (fecha)
);

-- ---------------------------------------------------------------------
-- Dim_Centro: incluye la jerarquía Centro > Zona en la misma dimensión
-- (igual que Ciudad/País en Geografía del ejemplo de clase).
-- ---------------------------------------------------------------------
CREATE TABLE dim_centro (
    centro_id       INTEGER PRIMARY KEY,        -- reutiliza centro_id operacional (natural key)
    nombre_centro   VARCHAR(100) NOT NULL,
    zona_id         INTEGER NOT NULL,
    nombre_zona     VARCHAR(50) NOT NULL         -- 'Los Lagos' | 'Aysén' | 'Magallanes'
);

-- ---------------------------------------------------------------------
-- Dim_Especie
-- ---------------------------------------------------------------------
CREATE TABLE dim_especie (
    especie_id      INTEGER PRIMARY KEY,
    nombre_especie  VARCHAR(50) NOT NULL         -- 'Salmón del Atlántico' | 'Salmón Coho' | 'Trucha'
);

-- ---------------------------------------------------------------------
-- Dim_Jaula
-- ---------------------------------------------------------------------
CREATE TABLE dim_jaula (
    jaula_id        INTEGER PRIMARY KEY,
    centro_id       INTEGER NOT NULL REFERENCES dim_centro(centro_id),
    capacidad       INTEGER NOT NULL
);

-- ---------------------------------------------------------------------
-- Dim_Lote (generación). SCD tipo 1: si cambia un atributo se sobrescribe,
-- porque el lote no cambia de identidad durante su ciclo de vida.
-- ---------------------------------------------------------------------
CREATE TABLE dim_lote (
    lote_id             INTEGER PRIMARY KEY,
    centro_id           INTEGER NOT NULL REFERENCES dim_centro(centro_id),
    jaula_id            INTEGER NOT NULL REFERENCES dim_jaula(jaula_id),
    especie_id          INTEGER NOT NULL REFERENCES dim_especie(especie_id),
    fecha_siembra_id    INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_id),
    smolts_sembrados    INTEGER NOT NULL
);

-- ---------------------------------------------------------------------
-- Dim_Alimento: tipo de alimento normalizado + proveedor.
-- NOTA (brecha de datos): origen_costos_alimento.csv trae variantes de
-- texto para el mismo tipo ('ENG-100' / 'engorda100' / 'Engorda 100').
-- El ETL debe normalizar a un único código antes de cargar esta tabla.
-- ---------------------------------------------------------------------
CREATE TABLE dim_alimento (
    alimento_id     INTEGER PRIMARY KEY,        -- surrogate
    tipo_alimento   VARCHAR(30) NOT NULL,        -- código normalizado, ej 'ENG-100'
    proveedor       VARCHAR(50) NOT NULL,
    UNIQUE (tipo_alimento, proveedor)
);

-- ---------------------------------------------------------------------
-- Dim_Calibre: rango de peso de cosecha
-- ---------------------------------------------------------------------
CREATE TABLE dim_calibre (
    calibre_id      INTEGER PRIMARY KEY,
    rango_calibre   VARCHAR(20) NOT NULL,        -- ej. '4-5 kg'
    kg_min          NUMERIC(5,2),
    kg_max          NUMERIC(5,2)
);

-- ---------------------------------------------------------------------
-- Dim_TipoEvento: catálogo de eventos sanitarios
-- ---------------------------------------------------------------------
CREATE TABLE dim_tipo_evento (
    tipo_evento_id      INTEGER PRIMARY KEY,
    tipo_evento         VARCHAR(30) NOT NULL,     -- 'SRS' | 'Caligus' | 'Branquitis'
    tratamiento_habitual VARCHAR(50)
);


-- =====================================================================
-- 2. TABLAS DE HECHOS
-- =====================================================================

-- ---------------------------------------------------------------------
-- Hecho_OperacionDiaria
-- Grano: 1 fila = 1 jaula en 1 día.
-- Fuente: operacion_diaria (sqlite)
-- alimento_kg, mortalidad_n y crecimiento_kg son ADITIVOS en el tiempo.
-- poblacion y biomasa_kg son STOCK (semi-aditivos): no se suman entre
-- días, se usa el último valor del período o el promedio.
-- temperatura_agua NO es aditiva: solo promedio.
-- ---------------------------------------------------------------------
CREATE TABLE hecho_operacion_diaria (
    tiempo_id           INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_id),
    centro_id           INTEGER NOT NULL REFERENCES dim_centro(centro_id),
    jaula_id            INTEGER NOT NULL REFERENCES dim_jaula(jaula_id),
    lote_id             INTEGER NOT NULL REFERENCES dim_lote(lote_id),
    especie_id          INTEGER NOT NULL REFERENCES dim_especie(especie_id),
    alimento_kg         NUMERIC(10,2) NOT NULL,
    mortalidad_n        INTEGER NOT NULL,
    poblacion            INTEGER NOT NULL,        -- stock, no aditivo en el tiempo
    biomasa_kg          NUMERIC(12,3) NOT NULL,   -- stock, no aditivo en el tiempo
    crecimiento_kg       NUMERIC(10,3) NOT NULL,
    temperatura_agua     NUMERIC(4,1),             -- no aditivo, promediar
    PRIMARY KEY (tiempo_id, jaula_id)
);

-- ---------------------------------------------------------------------
-- Hecho_Cosecha
-- Grano: 1 fila = 1 evento de cosecha de un lote.
-- Fuente: cosechas (sqlite)
-- ---------------------------------------------------------------------
CREATE TABLE hecho_cosecha (
    cosecha_id          INTEGER PRIMARY KEY,      -- natural key del origen
    tiempo_id            INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_id),
    centro_id            INTEGER NOT NULL REFERENCES dim_centro(centro_id),
    lote_id              INTEGER NOT NULL REFERENCES dim_lote(lote_id),
    calibre_id           INTEGER NOT NULL REFERENCES dim_calibre(calibre_id),
    kilos_vivos          NUMERIC(12,2) NOT NULL,
    kilos_producto       NUMERIC(12,2) NOT NULL,
    merma_pct            NUMERIC(5,2) GENERATED ALWAYS AS
                          (ROUND((1 - kilos_producto / NULLIF(kilos_vivos,0)) * 100, 2)) STORED
);

-- ---------------------------------------------------------------------
-- Hecho_EventoSanitario
-- Grano: 1 fila = 1 evento sanitario por centro.
-- Fuente: origen_eventos_sanitarios.json
-- Dim_Tiempo se referencia dos veces (dimensión de roles).
-- ---------------------------------------------------------------------
CREATE TABLE hecho_evento_sanitario (
    evento_id            VARCHAR(15) PRIMARY KEY,  -- natural key del origen, ej. 'EV-8001'
    tiempo_inicio_id      INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_id),
    tiempo_fin_id         INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_id),
    centro_id             INTEGER NOT NULL REFERENCES dim_centro(centro_id),
    tipo_evento_id        INTEGER NOT NULL REFERENCES dim_tipo_evento(tipo_evento_id),
    mortalidad_asociada    INTEGER NOT NULL,
    duracion_dias          INTEGER GENERATED ALWAYS AS (NULL) STORED  -- calcular en ETL: fecha_fin - fecha_inicio
);

-- Tabla puente para el atributo multivaluado jaulas_afectadas.
-- Permite analizar mortalidad de eventos sanitarios a nivel de jaula
-- sin romper el grano (1 fila = 1 evento) de Hecho_EventoSanitario.
CREATE TABLE puente_evento_jaula (
    evento_id       VARCHAR(15) NOT NULL REFERENCES hecho_evento_sanitario(evento_id),
    jaula_id        INTEGER NOT NULL REFERENCES dim_jaula(jaula_id),
    PRIMARY KEY (evento_id, jaula_id)
);

-- ---------------------------------------------------------------------
-- Hecho_CostoAlimento
-- Grano: 1 fila = 1 tipo de alimento en 1 mes.
-- Fuente: origen_costos_alimento.csv
-- precio_clp_kg NO es aditivo: es un punto/tarifa, se promedia o se usa
-- el último valor, nunca se suma entre meses o entre tipos.
-- ---------------------------------------------------------------------
CREATE TABLE hecho_costo_alimento (
    anio_mes             CHAR(7) NOT NULL,          -- 'YYYY-MM', FK lógica a dim_tiempo.anio_mes
    alimento_id           INTEGER NOT NULL REFERENCES dim_alimento(alimento_id),
    precio_clp_kg          NUMERIC(10,2) NOT NULL,
    moneda                 CHAR(3) NOT NULL DEFAULT 'CLP',
    glosa                  VARCHAR(100),
    PRIMARY KEY (anio_mes, alimento_id)
);


-- =====================================================================
-- 3. ÍNDICES RECOMENDADOS (consultas típicas: por centro y por fecha)
-- =====================================================================
CREATE INDEX ix_opdiaria_centro_tiempo   ON hecho_operacion_diaria (centro_id, tiempo_id);
CREATE INDEX ix_opdiaria_lote            ON hecho_operacion_diaria (lote_id);
CREATE INDEX ix_cosecha_centro_tiempo    ON hecho_cosecha (centro_id, tiempo_id);
CREATE INDEX ix_evento_centro            ON hecho_evento_sanitario (centro_id);
CREATE INDEX ix_costo_alimento_id        ON hecho_costo_alimento (alimento_id);


-- =====================================================================
-- 4. NOTAS DE INTEGRACIÓN (brechas de datos detectadas en el origen)
-- =====================================================================
-- a) hecho_operacion_diaria NO trae tipo_alimento en el origen, por lo
--    que no existe llave directa hacia dim_alimento / hecho_costo_alimento.
--    Definir con el negocio la regla de asignación (ej. un tipo de
--    alimento por especie+etapa, o un promedio ponderado por centro-mes)
--    antes de construir el costo real de alimentación por jaula.
-- b) origen_eventos_sanitarios.json trae centro_id 90-93, que no existen
--    en la tabla centros del sqlite: excluir en el staging como registros
--    de prueba, o crear un miembro "Centro desconocido" en dim_centro.
-- c) Formatos inconsistentes a normalizar en staging antes de esta carga:
--    fechas mixtas (dd/mm/yyyy vs yyyy-mm-dd), números como texto con
--    separador de miles/decimal variable, nombres de tipo_alimento con
--    variantes de mayúscula/guion/espacio, marcador de nulo "-".
-- =====================================================================
