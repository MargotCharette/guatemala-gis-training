## Módulo XX. Ejercicio de Análisis Ráster en QGIS

### Título
Estimación de la población expuesta a zonas de caída de ceniza volcánica en Guatemala

### Descripción General del Ejercicio
Este ejercicio práctico guía a los participantes a través de un análisis completo de exposición a amenazas volcánicas en Guatemala utilizando QGIS. Los participantes aprenderán a trabajar con datos raster y vectoriales, realizar análisis espaciales complejos, y crear mapas temáticos profesionales.

**¿Qué aprenderás?**
- Procesar y alinear datos raster de diferentes resoluciones y sistemas de coordenadas
- Crear máscaras binarias para análisis de exposición
- Calcular estadísticas zonales para resumir información por unidades administrativas
- Automatizar flujos de trabajo complejos usando el Diseñador de Modelos
- Crear mapas temáticos efectivos para comunicar resultados

**Contexto del problema:**
En Guatemala, la actividad volcánica representa un riesgo significativo para las poblaciones cercanas. Este ejercicio simula un análisis de exposición donde se identifican las zonas de riesgo (basadas en proximidad a volcanes) y se calcula cuántas personas viven en esas áreas. Los resultados se resumen por departamento para facilitar la toma de decisiones en gestión de riesgos.

**Duración estimada:** 2-3 horas (dependiendo de la experiencia del participante)

Nota (opcional, para formación avanzada): cargar datos a través de la consola de Python en QGIS.

### Objetivos
- Alinear capas ráster (resolución y grilla/alineación).
- Calcular población expuesta a amenaza volcánica (≥ “moderada”).
- Resumir por departamento (ADM1).
- Automatizar el flujo con Diseñador de modelos (Model Designer).

### 1) Abrir el proyecto y revisar capas
- Abra `QGIS_Project/guatemala_raster_training.qgz`.
- Verifique el CRS del proyecto: EPSG:32615 (UTM 15N). Si no hay CRS especificado, configúrelo en Proyecto → Propiedades → SRC o use el SRC de la capa Departamentos.

Capas esperadas:
- Departamentos (ADM1) – vector (`01_Vector/departamentos_gtm_adm1.shp`)
- Volcanes – vector (`01_Vector/volcanes_gtm.gpkg`)
- Población 2020 (100 m) – ráster (`02_Raster/GTM_ppp_v2b_2020_UNadj.tif`)
- Amenaza volcánica (sintética) – ráster (`02_Raster/hazard_volcanica_250m.tif`)

### Descripción breve de las capas
- **Departamentos (ADM1)**: polígonos de límites departamentales oficiales (nivel 1). Uso: agregación de resultados por departamento y referencia cartográfica. Campos clave: nombre del departamento.
- **Volcanes**: puntos con la ubicación de volcanes principales. Uso: referencia visual y generación de buffers de proximidad.
- **Población WorldPop 2020 (100 m)**: ráster de conteo de personas por píxel (100 m). CRS original: EPSG:4326 (WGS84). QGIS lo reproyecta “al vuelo” al SRC del proyecto (EPSG:32615). Valores esperados: ≥ 0; unidad: personas/píxel.
- **Amenaza volcánica (sintética)**: ráster categórico (250 m) derivado de anillos de proximidad a volcanes. Valores: 0 = fuera de zona; 1 = 20–30 km (baja); 2 = 10–20 km (moderada); 3 = 0–10 km (alta). Nota: capa de práctica; no usar para decisiones reales.
- **Máscara de país (opcional)**: polígono de Guatemala usado para recortes/definir extensión; no siempre se carga en el proyecto final.

✅ Chequeo: En Propiedades de cada ráster → Información: ambos deben estar en EPSG:32615 (metros). Resolución de población ≈ 100 m; de amenaza ≈ 250 m.

⚠️ **IMPORTANTE - Verificación de datos de población:**
- Abra la tabla de atributos del ráster de población o use Estadísticas ráster.
- Los valores deben ser **solo positivos** (0 a ~1000+ personas por píxel).
- **Nota:** Usamos directamente `GTM_ppp_v2b_2020_UNadj.tif` (datos originales WorldPop) para evitar problemas de recorte.
- Si ve valores **negativos**, verifique que el CRS del proyecto sea EPSG:32615.

### 2) Alinear la grilla de la amenaza volcánica a 100 m
Meta: evitar “desplazamientos” y celdas “mixtas” al combinar rásteres. Haremos que el ráster de amenaza tenga exactamente la misma resolución, origen y extensión que el de población (100 m), usando remuestreo por vecino más cercano (categorías).

Menú: Procesamiento → Caja de herramientas → GDAL → Proyección → Reproyección (warp) [Warped (reproject)].

Parámetros:
- Entrada: `02_Raster/hazard_volcanica_250m.tif`
- CRS destino: EPSG:32615
- Resolución destino: X = 100, Y = 100 (metros) [en inglés: "Output file resolution in target georeferenced units"]. Nota: en algunas instalaciones aparece como un único campo; escriba "100 100" (dos números separados por espacio). Si solo permite un número, introduzca `100` (se aplica a X e Y). Si no lo acepta, use "Parámetros adicionales de GDAL" con: `-tr 100 100`.
- Método de remuestreo: Nearest neighbour (categorías)
- Extensión destino: “…” → Usar la extensión de `GTM_ppp_v2b_2020_UNadj.tif`
- Salida: `02_Raster/hazard_volcanica_100m.tif`
 - Alineación de píxeles: active "Target aligned pixels" (si disponible) o, en parámetros adicionales de GDAL, añada: `-tap`.

Cargue el nuevo ráster y desactive el de 250 m.

✅ Chequeo: Resolución 100 m y coincidencia exacta con población (mismo tamaño y extensión).

### 3) Crear máscara binaria de exposición (≥ moderada) [8–10 min]
**Objetivo:** Convertir el ráster de amenaza volcánica (valores 0, 1, 2, 3) en una máscara binaria simple (0/1) que identifique las celdas expuestas a amenaza moderada o alta.

**¿Por qué es necesario?** Para calcular la población expuesta, necesitamos multiplicar la población por una máscara que sea 1 en zonas de riesgo y 0 en zonas seguras. El ráster de amenaza original tiene 4 clases, pero para el análisis de exposición solo necesitamos saber si una celda está expuesta (≥ moderada) o no.

Meta: 1 = celda expuesta (amenaza ≥ 2), 0 = no expuesta.

Menú: Procesamiento → Caja de herramientas → Raster calculator (QGIS).

Parámetros (Raster calculator - QGIS):
- Capas disponibles: asegúrese de tener cargado `02_Raster/hazard_volcanica_100m.tif`.
- Capa(s) de referencia (para extensión y resolución): seleccione `02_Raster/GTM_ppp_v2b_2020_UNadj.tif` (garantiza grilla 100 m y misma extensión).
- Extensión de salida: Usar capa(s) de referencia.
- CRS de salida: EPSG:32615.
- Tamaño de píxel X/Y: 100 100 (si aparece el campo; si no, se hereda de la capa de referencia).
- Valor NoData de salida: 0 (opcional, para evitar nulos en la máscara).
- Tipo de datos de salida: Byte/UInt8 (recomendado para binario), Int16 también es válido.

Expresión:
```
"hazard_volcanica_100m@1" >= 2
```

Descripción: compara, celda por celda, el valor del ráster de amenaza y devuelve 1 cuando la clase es ≥ 2 (expuesta) y 0 en caso contrario. En QGIS, los booleanos se manejan como 1/0. 

- Salida: `02_Raster/hazard_ge2_bin.tif`

Opcional (0/1 explícitos):
```
("hazard_volcanica_100m@1" >= 2) * 1
```

✅ Chequeo: Visualmente, las zonas cercanas a volcanes muestran 1; el resto 0.

Resultado visual e interpretación (no técnico)
- Simbología recomendada: Singleband pseudocolor (o Valores únicos).
  - Valor 0: transparente o gris claro.
  - Valor 1: rojo/amarillo intenso (destacado).
- En el mapa verás “manchas” alrededor de los volcanes: esas áreas son las potencialmente expuestas según el umbral elegido (≥ moderada).
- Lectura sencilla: 0 = fuera de la zona de exposición en este escenario; 1 = dentro. No es una probabilidad ni una intensidad, es un sí/no.
- Si “no ves nada”, puede que el 1 esté dibujado en negro: aplica la simbología anterior para distinguir 0 y 1.
- Controles rápidos:
  - Propiedades → Información: Mín = 0, Máx = 1.
  - Estadísticas/Valores únicos: deben aparecer 0 y 1.
  - Superpón con la capa de volcanes: la máscara 1 debe concentrarse cerca de ellos.
  - Si notas bordes “diente de sierra” o desplazados, revisa el paso 2 (alineación/extent).

### 4) Calcular "población expuesta" por celda [8–10 min]
**Objetivo:** Combinar la información de población con la máscara de exposición para identificar exactamente cuántas personas viven en las zonas de riesgo volcánico.

**¿Por qué es necesario?** Ahora tenemos dos rasters: uno con la población total por celda y otro con la máscara binaria (0/1) que identifica zonas expuestas. Al multiplicarlos, obtenemos un nuevo ráster donde solo las celdas expuestas conservan su valor de población, mientras que las celdas no expuestas se convierten en 0. Esto nos permite calcular la población total expuesta sumando todos los valores del ráster resultante.

Meta: multiplicar población por la máscara 0/1.

Menú: Procesamiento → Caja de herramientas → Raster calculator (QGIS).

Expresión:
```
"GTM_ppp_v2b_2020_UNadj@1" * "hazard_ge2_bin@1"
```

- Salida: `02_Raster/pop_expuesta_100m.tif`

Interpretación: en celdas no expuestas (0), la población queda 0; en expuestas, conserva el valor original.

### 5) Estadísticas zonales por departamento [12–15 min]
Meta: sumar población expuesta por ADM1.

**IMPORTANTE:** Antes de ejecutar Zonal Statistics, asegúrese de que la capa de departamentos esté cargada en el proyecto.

**Menú correcto:** Procesamiento → Caja de herramientas → Raster analysis → Zonal statistics (Estadísticas zonales).

**Alternativas si Zonal Statistics no funciona:**
- **Opción 1:** Procesamiento → Caja de herramientas → GDAL → Raster analysis → Zonal statistics
- **Opción 2:** Procesamiento → Caja de herramientas → SAGA → Vector → Zonal statistics
- **Opción 3:** Procesamiento → Caja de herramientas → GRASS → Raster → Zonal statistics

**Si ninguna opción permite seleccionar la capa de polígonos:**
- Verifique que `departamentos_gtm_adm1` sea una capa vectorial (polígono), no un ráster
- Intente recargar la capa: clic derecho → Recargar
- Reinicie QGIS si el problema persiste

Parámetros:
- **Capa de polígonos:** Seleccione desde la lista desplegable `departamentos_gtm_adm1` (debe estar cargada en el proyecto)
- **Ráster:** Seleccione desde la lista desplegable `pop_expuesta_100m` (debe estar cargada en el proyecto)
- **Estadísticos:** SUM (puede agregar MEAN/COUNT si lo desea)
- **Prefijo:** `exp_`

Resultado: la capa de departamentos tendrá nuevos campos, p. ej., `exp_sum`.
- Tabla de atributos → ordenar por `exp_sum` descendente. (Opcional) Exportar la tabla como CSV.

✅ Chequeo: Ningún valor `exp_sum` debería ser negativo; departamentos sin exposición tendrán 0.

### 6) Mapear y clasificar la exposición [10–12 min]
**Objetivo:** Visualizar y comunicar los resultados del análisis de exposición mediante la creación de un mapa temático que muestre la distribución espacial de la población expuesta por departamento.

**¿Por qué es necesario?** Los números por sí solos no cuentan toda la historia. Al crear un mapa con simbología apropiada, podemos identificar patrones geográficos, departamentos con mayor riesgo, y comunicar los hallazgos de manera efectiva a diferentes audiencias. La clasificación de datos nos ayuda a agrupar departamentos con niveles similares de exposición para facilitar la interpretación.

- Simbología → Relleno graduado sobre el campo `exp_sum`.
- Método: Quantile (5 clases) o Natural Breaks (Jenks).
- Mapa: añada etiquetas con el nombre del departamento y, opcionalmente, `exp_sum` formateado.
- (Opcional) Diseño de impresión: A4 vertical, título, leyenda, escala, norte y exportar a PDF.

### 7) Automatizar con Diseñador de modelos (Model Designer) [25–35 min]
**Objetivo:** Crear un modelo automatizado que permita ejecutar todo el flujo de análisis de exposición con un solo clic, facilitando la repetición del análisis con diferentes parámetros o para otros escenarios.

**¿Por qué es necesario?** Una vez que hemos desarrollado un flujo de trabajo exitoso, es importante poder reproducirlo fácilmente. El Model Designer nos permite encapsular todos los pasos (reproyección, máscara binaria, cálculo de exposición, estadísticas zonales) en un modelo reutilizable. Esto es especialmente útil para análisis de sensibilidad (cambiar umbrales), procesar nuevos datos, o compartir el flujo con otros usuarios.

Meta: un clic para generar exposición y tabla.

Menú: Procesamiento → Diseñador de modelos → Nuevo.

Entradas del modelo:
- `poblacion` (Raster layer; default: `02_Raster/GTM_ppp_v2b_2020_UNadj.tif`)
- `amenaza` (Raster layer; default: `02_Raster/hazard_volcanica_250m.tif`)
- `umbral` (Integer parameter; default = 2)
- `zonales` (Vector layer; default: `01_Vector/departamentos_gtm_adm1.shp`)

Nodos del modelo (arrastrar desde la Caja de herramientas):
1) GDAL → Proyección → Reproyección (warp)
   - Entrada: `@amenaza`
   - Target CRS: EPSG:32615; resolución 100 m; Extent = `@poblacion`
   - Resampling: Nearest neighbour
   - Output: `hazard_100m`
2) Raster calculator (QGIS) – binario
   - Expresión: `"hazard_100m@1" >= @umbral`
   - Salida: `hazard_bin`
3) Raster calculator (QGIS) – expuesta
   - Expresión: `"@poblacion@1" * "hazard_bin@1"`
   - Salida: `pop_expuesta`
4) Zonal statistics (Estadísticas zonales)
   - Polygons: `@zonales`
   - Raster: `pop_expuesta`
   - Stats: SUM; prefix `exp_`

Salidas del modelo:
- Agregue como Model Output el ráster `pop_expuesta` y la capa vectorial `@zonales` actualizada (con campos `exp_`).
- Guarde el modelo (p. ej., `exposicion_volcanica.model3`) y ejecútelo.

✅ Chequeo: cambie el umbral (1, 2, 3) y observe cómo varía `exp_sum`.

### 8) Validación rápida y buenas prácticas [5–8 min]
- CRS y resolución: ambos rásteres principales en EPSG:32615, 100 m.
- Remuestreo: Nearest neighbour para categorías (amenaza).
- Alineación: usar la extensión del ráster de población al reproyectar el de amenaza.
- NoData: si hay celdas NoData en población, se propaga a la exposición.
- Rendimiento: desactivar “Renderizar” durante procesos pesados; considere activar procesamiento en paralelo donde esté disponible.

### 9) Extensiones (opcionales)
- Cambio de umbral: mapas para ≥1, ≥2, =3.
- Exposición por municipio (ADM2): incorporar límites ADM2 y repetir Estadísticas zonales.
- Añadir centros de salud: calcular población expuesta a ≤10 km (buffer + AND lógico con máscara).
- Exportar resultados: CSV de `exp_sum` y PDF del mapa final.

### 10) Entregables sugeridos
- `02_Raster/hazard_volcanica_100m.tif`
- `02_Raster/hazard_ge2_bin.tif`
- `02_Raster/pop_expuesta_100m.tif`
- `01_Vector/departamentos_gtm_adm1_exposicion.gpkg` (departamentos con campo `exp_sum`)
- `mapa_exposicion_ADM1.pdf` (Layout exportado)

### Troubleshooting (rápido)
- “No aparecen volcanes”: use el ráster de amenaza ya incluido; la práctica no depende de la capa puntual.
- Rásteres no coinciden: repita la reproyección del hazard con Extent = población y resolución 100 m.
- Valores extraños en `exp_sum`: verifique que la máscara binaria sea 0/1 y que población sea “conteo por píxel” (no densidad reescalada).


