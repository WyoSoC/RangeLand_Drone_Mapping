#!/usr/bin/env python3
"""Build a ready-to-open, pre-styled QGIS project for a processed survey.

Run with QGIS's bundled Python (no GUI needed):
    QT_QPA_PLATFORM=offscreen /Applications/QGIS-*.app/Contents/MacOS/python \
        scripts/make_qgis_project.py processing/2026-05-21_Map \
        2026-05-21_Map/metadata/Images_Mapping_cameras.geojson \
        qgis/2026-05-21_Map.qgz  [docs/report/fig]

The project stores RELATIVE paths, so it works as long as the repository layout is kept
(qgis/ next to processing/). If a 4th argument is given, example map views are rendered
there as PNG (the same views you get in QGIS).
"""
import glob
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if not os.environ.get("PROJ_DATA"):
    exe = Path(sys.executable).resolve()
    for cand in glob.glob(str(exe.parents[1] / "Resources" / "qgis" / "proj")):
        os.environ["PROJ_DATA"] = cand

from qgis.core import (QgsApplication, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsPointCloudLayer,
                       QgsCoordinateReferenceSystem, QgsColorRampShader, QgsRasterShader,
                       QgsSingleBandPseudoColorRenderer, QgsStyle, QgsLineSymbol, QgsMarkerSymbol,
                       QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat, QgsTextBufferSettings,
                       QgsMapSettings, QgsMapRendererParallelJob, QgsRectangle, QgsRasterMinMaxOrigin,
                       QgsContrastEnhancement, QgsLayerTreeGroup)
try:
    from qgis.PyQt.QtGui import QColor, QPainter
    from qgis.PyQt.QtCore import QSize
except ImportError:  # Qt6 naming
    from PyQt6.QtGui import QColor, QPainter
    from PyQt6.QtCore import QSize

PROJ_DIR = Path(sys.argv[1]).resolve()
CAMERAS = Path(sys.argv[2]).resolve()
OUT = Path(sys.argv[3]).resolve()
FIGDIR = Path(sys.argv[4]).resolve() if len(sys.argv) > 4 else None

qgs = QgsApplication([], False)
qgs.initQgis()
project = QgsProject.instance()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:32613"))
project.setTitle(f"RangeLand DroneMaps: {PROJ_DIR.name}")
root = project.layerTreeRoot()
LAYERS = {}


def mode(name):
    """Qt5/Qt6-compatible QPainter composition mode."""
    cm = getattr(QPainter, "CompositionMode", QPainter)
    return getattr(cm, f"CompositionMode_{name}")


def add_raster(group, path, name, visible=True):
    p = PROJ_DIR / path
    if not p.exists():
        print("  (missing)", path)
        return None
    lyr = QgsRasterLayer(str(p), name)
    if not lyr.isValid():
        print("  (invalid)", path)
        return None
    project.addMapLayer(lyr, False)
    node = group.addLayer(lyr)
    node.setItemVisibilityChecked(visible)
    node.setExpanded(False)
    LAYERS[name] = lyr
    return lyr


def pseudocolor(lyr, ramp_name, vmin, vmax, invert=False, transparent_below=None, classes=None):
    ramp = QgsStyle.defaultStyle().colorRamp(ramp_name)
    if invert:
        ramp.invert()
    shader_fn = QgsColorRampShader(vmin, vmax, ramp)
    shader_fn.classifyColorRamp(classes or 10)
    if transparent_below is not None:
        items = shader_fn.colorRampItemList()
        items.insert(0, QgsColorRampShader.ColorRampItem(transparent_below, QColor(0, 0, 0, 0), f"< {transparent_below}"))
        shader_fn.setColorRampItemList(items)
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(shader_fn)
    r = QgsSingleBandPseudoColorRenderer(lyr.dataProvider(), 1, shader)
    r.setClassificationMin(vmin); r.setClassificationMax(vmax)
    lyr.setRenderer(r)


def multiply(lyr, opacity=0.5):
    lyr.setBlendMode(mode("Multiply"))
    lyr.renderer().setOpacity(opacity)


# ------------------------------------------------------------------ groups (top = drawn on top)
g_veg = root.addGroup("Vegetation (fine ground filter)")
g_terrain = root.addGroup("Terrain, corrected to USGS 3DEP (NAVD88)")
g_qa = root.addGroup("QA / accuracy")
g_raw = root.addGroup("ODM raw outputs (bowl-shaped heights)")
g_base = root.addGroup("Imagery")

# imagery + cameras
cam = QgsVectorLayer(str(CAMERAS), "Camera positions", "ogr")
if cam.isValid():
    cam.setRenderer(cam.renderer().clone())
    cam.renderer().setSymbol(QgsMarkerSymbol.createSimple({"name": "circle", "color": "255,60,60", "size": "1.2",
                                                           "outline_color": "white", "outline_width": "0.1"}))
    project.addMapLayer(cam, False)
    g_base.addLayer(cam).setItemVisibilityChecked(False)
    LAYERS["cameras"] = cam
add_raster(g_base, "odm_orthophoto/odm_orthophoto.tif", "Orthophoto 2 cm")

# terrain (corrected)
c = PROJ_DIR / "derived_navd88/contours_0.25m.gpkg"
if c.exists():
    lyr = QgsVectorLayer(f"{c}|layername=contour", "Contours 0.25 m (NAVD88)", "ogr")
    if not lyr.isValid():
        lyr = QgsVectorLayer(str(c), "Contours 0.25 m (NAVD88)", "ogr")
    lyr.renderer().setSymbol(QgsLineSymbol.createSimple({"color": "60,40,20,200", "width": "0.2"}))
    pal = QgsPalLayerSettings()
    pal.fieldName = "CASE WHEN \"elev_m\" % 1 = 0 THEN format_number(\"elev_m\", 0) END"
    pal.isExpression = True
    pal.placement = getattr(QgsPalLayerSettings, "Line", 2)
    fmt = QgsTextFormat(); fmt.setSize(7)
    buf = QgsTextBufferSettings(); buf.setEnabled(True); buf.setSize(0.7); fmt.setBuffer(buf)
    pal.setFormat(fmt)
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(pal)); lyr.setLabelsEnabled(True)
    project.addMapLayer(lyr, False)
    g_terrain.addLayer(lyr)
    LAYERS["contours"] = lyr
hs = add_raster(g_terrain, "derived_navd88/dtm_hillshade.tif", "DTM hillshade")
if hs:
    multiply(hs, 0.6)
dtm = add_raster(g_terrain, "corrected/dtm_navd88.tif", "DTM corrected (NAVD88)")
if dtm:
    pseudocolor(dtm, "Spectral", 2185.5, 2191.0, invert=True)
sl = add_raster(g_terrain, "derived_navd88/dtm_slope_deg_1m.tif", "Terrain slope 1 m (deg)", visible=False)
if sl:
    pseudocolor(sl, "Magma", 0, 8, invert=True)
dsm = add_raster(g_terrain, "corrected/dsm_navd88.tif", "DSM corrected (NAVD88)", visible=False)
if dsm:
    pseudocolor(dsm, "Spectral", 2185.5, 2191.0, invert=True)
dhs = add_raster(g_terrain, "derived_navd88/dsm_hillshade.tif", "DSM hillshade", visible=False)

# vegetation
cov = add_raster(g_veg, "vegetation/veg_cover_1m.tif", "Vegetation cover >= 10 cm (fraction, 1 m)", visible=False)
if cov:
    pseudocolor(cov, "Greens", 0.0, 0.5, transparent_below=0.02)
chm = add_raster(g_veg, "vegetation/chm_10cm.tif", "Vegetation height, max HAG (m, 10 cm)", visible=False)
if chm:
    pseudocolor(chm, "YlGn", 0.0, 0.3, transparent_below=0.05)
mask = add_raster(g_veg, "vegetation/veg_mask_10cm.tif", "Vegetation mask >= 10 cm", visible=False)
if mask:
    pseudocolor(mask, "Greens", 0, 1, transparent_below=0.5, classes=2)
pc = PROJ_DIR / "vegetation/classified_hag.laz"
if pc.exists() and os.environ.get("ADD_POINTCLOUD", "1") == "1":
    pcl = QgsPointCloudLayer(str(pc), "Point cloud (classified, HeightAboveGround)", "pdal")
    if pcl.isValid():
        project.addMapLayer(pcl, False)
        g_veg.addLayer(pcl).setItemVisibilityChecked(False)

# QA
diff = add_raster(g_qa, "reference/diff_drone_minus_3dep.tif", "Raw drone DTM minus 3DEP (m)", visible=False)
if diff:
    pseudocolor(diff, "RdBu", -45, -31, invert=True)
res = add_raster(g_qa, "reference/residual_after_fit.tif", "Residual after correction (m)", visible=False)
if res:
    pseudocolor(res, "RdBu", -0.5, 0.5, invert=True)
usgs = add_raster(g_qa, "reference/usgs_3dep_2m.tif", "USGS 3DEP lidar DEM 2 m", visible=False)
if usgs:
    pseudocolor(usgs, "Spectral", 2185.5, 2191.0, invert=True)

# raw ODM
for path, name in [("odm_dem/dtm.tif", "ODM DTM raw"), ("odm_dem/dsm.tif", "ODM DSM raw"),
                   ("derived/dtm_hillshade.tif", "ODM DTM hillshade raw")]:
    lyr = add_raster(g_raw, path, name, visible=False)
    if lyr and "hillshade" not in path:
        pseudocolor(lyr, "Spectral", 2142, 2159, invert=True)
for g in (g_raw, g_qa):
    g.setExpanded(False)

# initial view: whole site
ext = LAYERS["Orthophoto 2 cm"].extent()
project.viewSettings().setDefaultViewExtent(
    __import__("qgis.core", fromlist=["QgsReferencedRectangle"]).QgsReferencedRectangle(ext, project.crs()))

OUT.parent.mkdir(parents=True, exist_ok=True)
project.writeEntryBool("Paths", "/Absolute", False)
project.write(str(OUT))
print("wrote", OUT)


# ------------------------------------------------------------------ example renders
def render(names, extent, fname, width=1400):
    ms = QgsMapSettings()
    ms.setLayers([LAYERS[n] for n in names if n in LAYERS])
    ms.setDestinationCrs(project.crs())
    ms.setExtent(extent)
    h = int(width * extent.height() / extent.width())
    ms.setOutputSize(QSize(width, h))
    ms.setBackgroundColor(QColor(255, 255, 255))
    job = QgsMapRendererParallelJob(ms)
    job.start(); job.waitForFinished()
    job.renderedImage().save(str(FIGDIR / fname), "png")
    print("wrote", FIGDIR / fname)


if FIGDIR:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    site = ext
    zoom = QgsRectangle(443920, 4569380, 444120, 4569530)
    render(["contours", "Orthophoto 2 cm"], zoom, "09_qgis_ortho_contours.png")
    render(["contours", "DTM hillshade", "DTM corrected (NAVD88)"], site, "10_qgis_terrain.png")
    render(["Vegetation cover >= 10 cm (fraction, 1 m)", "Orthophoto 2 cm"], site, "11_qgis_cover_on_ortho.png")
    render(["Vegetation height, max HAG (m, 10 cm)", "Orthophoto 2 cm"], QgsRectangle(443990, 4569430, 444040, 4569470),
           "12_qgis_vegheight_zoom.png")

qgs.exitQgis()
