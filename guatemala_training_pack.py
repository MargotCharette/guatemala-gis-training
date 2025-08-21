# -*- coding: utf-8 -*-
"""
PyQGIS — Paquete de datos para taller Guatemala (compatible sin importdelimitedtext)
- Carpeta de salida (diálogo)
- ADM1 geoBoundaries (API -> fallback GitHub)
- Volcanes: NOAA CSV -> fallback GVP WFS -> fallback CSV manual (6 volcanes)
- Importación CSV robusta (qgis/native importdelimitedtext -> delimitedtext -> guardar)
- WorldPop 2020 UN-adjusted (selector si no está)
- Raster sintético de amenaza volcánica (250 m) alineado a WorldPop
- Proyecto QGIS .qgz
"""
print("# ==========================")
import os
import json
import csv
import shutil
import urllib.request
import urllib.error
from datetime import datetime
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer, QgsApplication
from qgis.PyQt import QtWidgets
import processing

def print_progress(message):
    """Print progress message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def safe_download(url, dest, timeout=60):
    """Download with better error handling and progress feedback"""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print_progress(f"Archivo ya existe: {os.path.basename(dest)}")
        return dest
    
    print_progress(f"Descargando: {url}")
    try:
        urllib.request.urlretrieve(url, dest)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print_progress(f"✅ Descarga completada: {os.path.basename(dest)}")
            return dest
        else:
            raise RuntimeError("Archivo descargado está vacío o no existe")
    except Exception as e:
        if os.path.exists(dest):
            os.remove(dest)  # Clean up failed download
        raise RuntimeError(f"Error descargando {url}: {str(e)}")

def unzip(zfile, to_dir):
    """Extract archive with error handling"""
    try:
        print_progress(f"Extrayendo: {os.path.basename(zfile)}")
        shutil.unpack_archive(zfile, to_dir)
        print_progress("✅ Extracción completada")
    except Exception as e:
        raise RuntimeError(f"Error extrayendo {zfile}: {str(e)}")

def find_first_by_ext(root_dir, exts=(".shp", ".geojson", ".json")):
    """Find first file with specified extensions"""
    for r, _, files in os.walk(root_dir):
        for fn in files:
            if fn.lower().endswith(exts):
                return os.path.join(r, fn)
    return None

def raster_extent_str(path):
    """Get raster extent as string for GDAL operations"""
    rlyr = QgsRasterLayer(path, "ref", "gdal")
    if not rlyr.isValid():
        raise RuntimeError(f"No se pudo cargar el raster: {path}")
    ext = rlyr.extent()
    return f"{ext.xMinimum()},{ext.xMaximum()},{ext.yMinimum()},{ext.yMaximum()}"

def import_csv_points(csv_path, x_field, y_field, out_gpkg):
    """
    Intenta importar CSV -> puntos con:
      1) qgis:importdelimitedtext
      2) native:importdelimitedtext
      3) Proveedor 'delimitedtext' + guardado a GPKG
    Devuelve ruta a GPKG con puntos.
    """
    print_progress(f"Importando CSV: {os.path.basename(csv_path)}")
    
    params = {
        "INPUT": csv_path,
        "DELIMITER": ",",
        "XFIELD": x_field,
        "YFIELD": y_field,
        "WKT_FIELD": "",
        "CRS": "EPSG:4326",
        "GEOMETRY": "Point",
        "HEADERS": 1,
        "OUTPUT": out_gpkg
    }
    
    # Try processing algorithms first
    for alg in ("qgis:importdelimitedtext", "native:importdelimitedtext"):
        try:
            print_progress(f"Intentando con {alg}")
            processing.run(alg, params)
            lyr = QgsVectorLayer(out_gpkg, "tmp", "ogr")
            if lyr.isValid() and lyr.featureCount() > 0:
                print_progress(f"✅ CSV importado con {alg}")
                return out_gpkg
        except Exception as e:
            print_progress(f"⚠️ {alg} falló: {str(e)}")
            continue
    
    # Fallback: provider delimitedtext
    print_progress("Usando proveedor delimitedtext como fallback")
    uri = f"file:///{csv_path}?delimiter=,&xField={x_field}&yField={y_field}&crs=epsg:4326"
    lyr = QgsVectorLayer(uri, "csv_points", "delimitedtext")
    
    if not lyr.isValid():
        raise RuntimeError("No se pudo leer el CSV como puntos (delimitedtext).")
    
    if lyr.featureCount() == 0:
        raise RuntimeError("CSV no contiene features válidas.")
    
    # Guardar: intentar savefeatures, si no, reprojectlayer
    try:
        processing.run("native:savefeatures", {"INPUT": lyr, "OUTPUT": out_gpkg})
    except Exception:
        processing.run("native:reprojectlayer", {
            "INPUT": lyr,
            "TARGET_CRS": "EPSG:4326",
            "OUTPUT": out_gpkg
        })
    
    lyr2 = QgsVectorLayer(out_gpkg, "tmp2", "ogr")
    if not (lyr2.isValid() and lyr2.featureCount() > 0):
        raise RuntimeError("Fallo al guardar el CSV como GPKG.")
    
    print_progress(f"✅ CSV importado con delimitedtext: {lyr2.featureCount()} features")
    return out_gpkg

def main():
    """Main execution function"""
    print("🚀 Iniciando creación del paquete de entrenamiento Guatemala...")
    
    # ---------- UI: carpeta de salida ----------
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication([])
    
    out_root = QtWidgets.QFileDialog.getExistingDirectory(
        None, "Selecciona la carpeta DESTINO (mejor una carpeta vacía)"
    )
    if not out_root:
        print("❌ No se seleccionó carpeta. Saliendo.")
        return
    
    OUTPUT_ROOT = out_root
    VEC_DIR = os.path.join(OUTPUT_ROOT, "01_Vector")
    RAS_DIR = os.path.join(OUTPUT_ROOT, "02_Raster")
    PRJ_DIR = os.path.join(OUTPUT_ROOT, "QGIS_Project")
    
    for d in (VEC_DIR, RAS_DIR, PRJ_DIR):
        os.makedirs(d, exist_ok=True)
        print_progress(f"📁 Carpeta creada: {d}")
    
    CRS_TARGET = "EPSG:32615"  # UTM 15N
    
    try:
        # ---------- 1) ADM1 (geoBoundaries) ----------
        print_progress("🌍 Obteniendo límites administrativos (ADM1)...")
        adm1_path = None
        
        try:
            gb_api = "https://www.geoboundaries.org/api/current/gbOpen/GTM/ADM1/"
            with urllib.request.urlopen(gb_api, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            
            item = data[0] if isinstance(data, list) else data
            shp_url = item.get("shpDownloadURL") or item.get("shpURL")
            gj_url = item.get("gjDownloadURL") or item.get("geojsonDownloadURL")
            
            if shp_url:
                adm1_zip = os.path.join(VEC_DIR, "geoBoundaries-GTM-ADM1.zip")
                safe_download(shp_url, adm1_zip)
                unzip(adm1_zip, VEC_DIR)
                adm1_path = find_first_by_ext(VEC_DIR, exts=(".shp",))
            elif gj_url:
                adm1_path = safe_download(gj_url, os.path.join(VEC_DIR, "geoBoundaries-GTM-ADM1.geojson"))
            else:
                raise RuntimeError("API sin URL de descarga.")
                
        except Exception as e:
            print_progress(f"⚠️ API geoBoundaries falló, usando fallback: {e}")
            gb_fallback = "https://raw.githubusercontent.com/wmgeolab/geoBoundaries/main/releaseData/gbOpen/GTM/ADM1/geoBoundaries-GTM-ADM1.geojson"
            adm1_path = safe_download(gb_fallback, os.path.join(VEC_DIR, "geoBoundaries-GTM-ADM1.geojson"))
        
        if not adm1_path or not os.path.exists(adm1_path):
            raise RuntimeError("No se pudo obtener ADM1 de Guatemala.")
        
        print_progress("✅ ADM1 obtenido, procesando...")
        adm1_raw = QgsVectorLayer(adm1_path, "ADM1_raw", "ogr")
        if not adm1_raw.isValid():
            raise RuntimeError("ADM1 inválido.")
        
        # Reproject to UTM
        adm1_utm = os.path.join(VEC_DIR, "departamentos_gtm_adm1.shp")
        processing.run("native:reprojectlayer", {
            "INPUT": adm1_raw,
            "TARGET_CRS": CRS_TARGET,
            "OUTPUT": adm1_utm
        })
        
        # Create country mask
        mask_country = os.path.join(VEC_DIR, "guatemala_mask.shp")
        processing.run("native:dissolve", {
            "INPUT": adm1_utm,
            "FIELD": [],
            "SEPARATE_DISJOINT": False,
            "OUTPUT": mask_country
        })
        print_progress("✅ Máscara de país creada")
        
        # ---------- 2) Volcanes (NOAA -> GVP -> CSV manual) ----------
        print_progress("🌋 Obteniendo datos de volcanes...")
        volc_layer = None
        
        # Try NOAA CSV first
        noaa_csv_url = "https://www.ncei.noaa.gov/pub/data/volcano/Global_Volcano_Locations_Database.csv"
        volc_csv = os.path.join(VEC_DIR, "volcanes_global_noaa.csv")
        
        try:
            safe_download(noaa_csv_url, volc_csv)
            volc_points = os.path.join(VEC_DIR, "volcanes_global.gpkg")
            import_csv_points(volc_csv, "Longitude", "Latitude", volc_points)
            volc_layer = QgsVectorLayer(volc_points, "Volcanes_WGS84", "ogr")
            print_progress("✅ Volcanes NOAA obtenidos")
        except Exception as e:
            print_progress(f"⚠️ NOAA CSV falló: {e}")
        
        # Try GVP WFS if NOAA failed
        if volc_layer is None or not volc_layer.isValid():
            gvp_geojson = ("https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows"
                          "?service=WFS&version=1.0.0&request=GetFeature"
                          "&typeName=GVP-VOTW:volcanoes&outputFormat=application/json")
            volc_geojson_path = os.path.join(VEC_DIR, "volcanes_gvp.geojson")
            
            try:
                safe_download(gvp_geojson, volc_geojson_path)
                volc_layer = QgsVectorLayer(volc_geojson_path, "Volcanes_WGS84", "ogr")
                print_progress("✅ Volcanes GVP obtenidos")
            except Exception as e:
                print_progress(f"⚠️ GVP WFS falló: {e}")
        
        # Use manual CSV as final fallback
        if volc_layer is None or not volc_layer.isValid():
            print_progress("📝 Usando CSV manual de respaldo con 6 volcanes de Guatemala")
            manual_csv = os.path.join(VEC_DIR, "volcanes_gtm_manual.csv")
            
            with open(manual_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Name", "Longitude", "Latitude"])
                w.writerow(["Fuego", -90.880, 14.473])
                w.writerow(["Pacaya", -90.601, 14.381])
                w.writerow(["Acatenango", -90.876, 14.501])
                w.writerow(["Agua", -90.744, 14.465])
                w.writerow(["Santa_Maria", -91.552, 14.756])
                w.writerow(["Tajumulco", -91.904, 15.043])
            
            volc_points = os.path.join(VEC_DIR, "volcanes_manual.gpkg")
            import_csv_points(manual_csv, "Longitude", "Latitude", volc_points)
            volc_layer = QgsVectorLayer(volc_points, "Volcanes_WGS84", "ogr")
        
        # BBOX preliminar en WGS84 para reducir ruido: (-92.5, -88.0, 13.5, 18.0)
        volc_bbox = os.path.join(VEC_DIR, "volcanes_bbox.gpkg")
        processing.run("native:extractbyextent", {
            "INPUT": volc_layer,
            "EXTENT": "-92.5,-88.0,13.5,18.0",
            "CLIP": True,
            "OUTPUT": volc_bbox
        })
        
        volc_bbox_lyr = QgsVectorLayer(volc_bbox, "Volcanes_bbox", "ogr")
        
        # Reproject to UTM and clip to Guatemala
        volc_prj = os.path.join(VEC_DIR, "volcanes_prj.gpkg")
        processing.run("native:reprojectlayer", {
            "INPUT": volc_bbox_lyr,
            "TARGET_CRS": CRS_TARGET,
            "OUTPUT": volc_prj
        })
        
        volc_gtm = os.path.join(VEC_DIR, "volcanes_gtm.gpkg")
        processing.run("native:extractbylocation", {
            "INPUT": volc_prj,
            "PREDICATE": [0],
            "INTERSECT": mask_country,
            "OUTPUT": volc_gtm
        })
        
        volc_gtm_lyr = QgsVectorLayer(volc_gtm, "Volcanes_GTM", "ogr")
        
        if (not volc_gtm_lyr.isValid()) or (volc_gtm_lyr.featureCount() == 0):
            volc_gtm = os.path.join(VEC_DIR, "volcanes_gtm_clip.gpkg")
            processing.run("native:clip", {
                "INPUT": volc_prj,
                "OVERLAY": mask_country,
                "OUTPUT": volc_gtm
            })
            volc_gtm_lyr = QgsVectorLayer(volc_gtm, "Volcanes_GTM", "ogr")
        
        if (not volc_gtm_lyr.isValid()) or (volc_gtm_lyr.featureCount() == 0):
            raise RuntimeError("No se encontraron volcanes dentro del límite de Guatemala tras todos los fallbacks.")
        
        print_progress(f"✅ Volcanes procesados: {volc_gtm_lyr.featureCount()} features")
        
        # ---------- 3) WorldPop (selector si no está) ----------
        print_progress("👥 Procesando datos de población WorldPop...")
        WORLDPOP_FILE_NAME = "GTM_ppp_v2b_2020_UNadj.tif"
        worldpop_src = os.path.join(RAS_DIR, WORLDPOP_FILE_NAME)
        
        if not os.path.exists(worldpop_src):
            picked, _ = QtWidgets.QFileDialog.getOpenFileName(
                None,
                "Selecciona el raster WorldPop Guatemala 2020 UN-adjusted (GeoTIFF)",
                OUTPUT_ROOT,
                "GeoTIFF (*.tif *.tiff)"
            )
            if not picked:
                raise RuntimeError("No se encontró el raster de WorldPop. Descárgalo (UN-adjusted, 100 m) y vuelve a intentar.")
            shutil.copy(picked, worldpop_src)
            print_progress("✅ WorldPop copiado a la carpeta de destino")
        
        # Use original WorldPop file directly (no reprojection/clipping needed)
        worldpop_clip = worldpop_src  # Keep original file path for consistency
        print_progress("✅ WorldPop original usado directamente")
        
        # ---------- 4) Amenaza volcánica sintética (250 m) ----------
        print_progress("🔥 Generando raster de amenaza volcánica...")
        
        def add_level(src_path, level, out_path):
            processing.run("qgis:fieldcalculator", {
                "INPUT": src_path,
                "FIELD_NAME": "level",
                "FIELD_TYPE": 1,
                "FIELD_LENGTH": 2,
                "FIELD_PRECISION": 0,
                "NEW_FIELD": True,
                "FORMULA": str(level),
                "OUTPUT": out_path
            })
            return out_path
        
        # Create buffers
        buf10_raw = os.path.join(VEC_DIR, "buf10km_raw.gpkg")
        processing.run("native:buffer", {
            "INPUT": volc_gtm_lyr,
            "DISTANCE": 10000,
            "SEGMENTS": 16,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "DISSOLVE": True,
            "OUTPUT": buf10_raw
        })
        buf10 = add_level(buf10_raw, 3, os.path.join(VEC_DIR, "buf10km.gpkg"))
        
        buf20_raw = os.path.join(VEC_DIR, "buf20km_raw.gpkg")
        processing.run("native:buffer", {
            "INPUT": volc_gtm_lyr,
            "DISTANCE": 20000,
            "SEGMENTS": 16,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "DISSOLVE": True,
            "OUTPUT": buf20_raw
        })
        buf20 = add_level(buf20_raw, 2, os.path.join(VEC_DIR, "buf20km.gpkg"))
        
        buf30_raw = os.path.join(VEC_DIR, "buf30km_raw.gpkg")
        processing.run("native:buffer", {
            "INPUT": volc_gtm_lyr,
            "DISTANCE": 30000,
            "SEGMENTS": 16,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "DISSOLVE": True,
            "OUTPUT": buf30_raw
        })
        buf30 = add_level(buf30_raw, 1, os.path.join(VEC_DIR, "buf30km.gpkg"))
        
        # Build non-overlapping rings to preserve classes in rasterization
        ring30 = os.path.join(VEC_DIR, "ring_30km.gpkg")
        processing.run("native:difference", {
            "INPUT": buf30,
            "OVERLAY": buf20,
            "OUTPUT": ring30
        })
        ring20 = os.path.join(VEC_DIR, "ring_20_10km.gpkg")
        processing.run("native:difference", {
            "INPUT": buf20,
            "OVERLAY": buf10,
            "OUTPUT": ring20
        })
        ring10 = buf10  # inner ring remains as-is
        
        # Merge and dissolve (rings do not overlap; dissolve is optional)
        merged = os.path.join(VEC_DIR, "haz_buffers_merged.gpkg")
        processing.run("native:mergevectorlayers", {
            "LAYERS": [ring30, ring20, ring10],
            "OUTPUT": merged
        })
        
        haz_diss = os.path.join(VEC_DIR, "haz_buffers_diss.gpkg")
        processing.run("native:dissolve", {
            "INPUT": merged,
            "FIELD": ["level"],
            "SEPARATE_DISJOINT": False,
            "OUTPUT": haz_diss
        })
        
        # Rasterize
        haz_raster = os.path.join(RAS_DIR, "hazard_volcanica_250m.tif")
        
        # Get extent from the country mask (which is in the target CRS) instead of population raster
        mask_lyr = QgsVectorLayer(mask_country, "mask", "ogr")
        if not mask_lyr.isValid():
            raise RuntimeError("No se pudo cargar la máscara de país para obtener la extensión")
        
        ext = mask_lyr.extent()
        extent_str = f"{ext.xMinimum()},{ext.xMaximum()},{ext.yMinimum()},{ext.yMaximum()}"
        
        processing.run("gdal:rasterize", {
            "INPUT": haz_diss,
            "FIELD": "level",
            "UNITS": 1,
            "WIDTH": 250,
            "HEIGHT": 250,
            "EXTENT": extent_str,
            "NODATA": 0,
            "DATA_TYPE": 1,
            "INIT": 0,
            "INVERT": False,
            "OUTPUT": haz_raster
        })
        print_progress("✅ Raster de amenaza volcánica generado")
        
        # ---------- 5) Proyecto QGIS & README ----------
        print_progress("🗺️ Creando proyecto QGIS...")
        prj = QgsProject.instance()
        prj.clear()
        
        # Add layers in logical order (background to foreground)
        prj.addMapLayer(QgsVectorLayer(adm1_utm, "Departamentos (ADM1)", "ogr"))
        prj.addMapLayer(QgsVectorLayer(volc_gtm, "Volcanes", "ogr"))
        prj.addMapLayer(QgsRasterLayer(worldpop_clip, f"Población WorldPop 2020 (100 m) - {WORLDPOP_FILE_NAME}", "gdal"))
        prj.addMapLayer(QgsRasterLayer(haz_raster, "Amenaza volcánica (sintética)", "gdal"))
        
        project_path = os.path.join(PRJ_DIR, "guatemala_raster_training.qgz")
        prj.write(project_path)
        
        # Create README
        readme_path = os.path.join(OUTPUT_ROOT, "README.txt")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(
                f"PAQUETE DE ENTRENAMIENTO QGIS - GUATEMALA\n"
                f"==========================================\n\n"
                f"Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"CONTENIDO:\n"
                f"----------\n"
                f"• Límites administrativos (ADM1) - departamentos_gtm_adm1.shp\n"
                f"• Máscara de país - guatemala_mask.shp\n"
                f"• Volcanes - volcanes_gtm.gpkg\n"
                f"• Población WorldPop 2020 (UN-adjusted, 100 m) - {WORLDPOP_FILE_NAME}\n"
                f"• Raster sintético de amenaza volcánica (250 m) - hazard_volcanica_250m.tif\n\n"
                f"CRS: EPSG:32615 (UTM 15N - Zona 15 Norte)\n\n"
                f"ESTRUCTURA DE CARPETAS:\n"
                f"----------------------\n"
                f"01_Vector/     - Capas vectoriales\n"
                f"02_Raster/     - Rasters de población y amenaza\n"
                f"QGIS_Project/  - Proyecto QGIS (.qgz)\n\n"
                f"USO:\n"
                f"----\n"
                f"1. Abrir guatemala_raster_training.qgz en QGIS\n"
                f"2. Todas las capas están precargadas y proyectadas\n"
                f"3. Listo para análisis y visualización\n\n"
                f"Ubicación: {OUTPUT_ROOT}\n"
            )
        
        print_progress("✅ Proyecto QGIS y README creados")
        
        # Final success message
        print("\n" + "="*60)
        print("🎉 ¡PAQUETE DE ENTRENAMIENTO COMPLETADO EXITOSAMENTE!")
        print("="*60)
        print(f"📂 Carpeta principal: {OUTPUT_ROOT}")
        print(f"🗺️ Proyecto QGIS: {project_path}")
        print(f"📖 README: {readme_path}")
        print(f"🌍 Capas vectoriales: {VEC_DIR}")
        print(f"🖼️ Rasters: {RAS_DIR}")
        print("="*60)
        print("✅ El paquete está listo para usar en talleres de QGIS.")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print("El proceso se detuvo debido a un error.")
        return False
    
    return True


# if __name__ == "__main__":
success = main()
if not success:
    print("\n💡 Sugerencias para resolver problemas:")
    print("- Verifica tu conexión a internet")
    print("- Asegúrate de tener permisos de escritura en la carpeta destino")
    print("- Si el error persiste, intenta ejecutar el script nuevamente")