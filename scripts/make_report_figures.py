#!/usr/bin/env python3
"""Make the figures for docs/REPORT.md from a processed project.

Run with a Python that has GDAL + numpy + matplotlib, e.g. QGIS's bundled Python:
    /Applications/QGIS-*.app/Contents/MacOS/python scripts/make_report_figures.py \
        processing/2026-05-21_Map 2026-05-21_Map/metadata/Images_Mapping_inventory.csv docs/report/fig

Expects the outputs of run_odm.sh, postprocess.sh (+ derived_navd88), vegetation_chm.sh,
correct_dem_3dep.py, and the PDAL cross-section CSVs in vegetation/sections/.
"""
import csv
import glob
import json
import os
import sys
from pathlib import Path

if not os.environ.get("PROJ_DATA"):
    exe = Path(sys.executable).resolve()
    for cand in glob.glob(str(exe.parents[1] / "Resources" / "qgis" / "proj")) + ["/opt/homebrew/share/proj"]:
        if Path(cand, "proj.db").exists():
            os.environ["PROJ_DATA"] = cand
            break

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, Normalize
import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()
plt.rcParams.update({"font.size": 9, "axes.titlesize": 10, "figure.dpi": 110, "savefig.bbox": "tight"})

P = Path(sys.argv[1])
INV = Path(sys.argv[2])
OUT = Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)

ORTHO = P / "odm_orthophoto/odm_orthophoto.tif"
DSM_RAW, DTM_RAW = P / "odm_dem/dsm.tif", P / "odm_dem/dtm.tif"
DSM, DTM = P / "corrected/dsm_navd88.tif", P / "corrected/dtm_navd88.tif"
USGS = P / "reference/usgs_3dep_2m.tif"
DIFF, RESID = P / "reference/diff_drone_minus_3dep.tif", P / "reference/residual_after_fit.tif"
SLOPE = P / "derived_navd88/dtm_slope_deg_1m.tif"
CONTOURS = P / "derived_navd88/contours_0.25m.gpkg"
CHM_VEG, COVER = P / "vegetation/chm_10cm.tif", P / "vegetation/veg_cover_1m.tif"
MASK = P / "vegetation/veg_mask_10cm.tif"

# full-site window (from the DSM grid)
_d = gdal.Open(str(DSM_RAW)); _gt = _d.GetGeoTransform()
SITE = (_gt[0], _gt[3] + _gt[5] * _d.RasterYSize, _gt[0] + _gt[1] * _d.RasterXSize, _gt[3])  # xmin,ymin,xmax,ymax
_d = None


def read(path, bounds=SITE, res=None, width=None, band=None, alg="average"):
    """Read a raster window resampled to res (m) or width (px). Returns (array, extent)."""
    xmin, ymin, xmax, ymax = bounds
    kw = dict(format="MEM", outputBounds=bounds, resampleAlg=alg)
    if res:
        kw.update(xRes=res, yRes=res)
    else:
        kw.update(width=width, height=int(width * (ymax - ymin) / (xmax - xmin)))
    if band:
        kw["srcBands"] = [band] if isinstance(band, int) else band
    ds = gdal.Warp("", str(path), **kw)
    arrs = []
    for b in range(1, ds.RasterCount + 1):
        rb = ds.GetRasterBand(b)
        a = rb.ReadAsArray().astype(np.float64)
        nd = rb.GetNoDataValue()
        if nd is not None:
            a[a == nd] = np.nan
        arrs.append(a)
    arr = arrs[0] if len(arrs) == 1 else np.dstack(arrs)
    return arr, (xmin, xmax, ymin, ymax)


def ortho_rgb(bounds=SITE, width=1400):
    a, ext = read(ORTHO, bounds, width=width, band=[1, 2, 3, 4])
    rgb = a[..., :3] / 255.0
    alpha = a[..., 3] > 0
    rgb[~alpha] = 1.0
    return rgb, ext


def hillshade(z, res, exag=1.0):
    ls = LightSource(azdeg=315, altdeg=45)
    zz = np.where(np.isfinite(z), z, np.nanmean(z))
    return ls.hillshade(zz, vert_exag=exag, dx=res, dy=res)


def scalebar(ax, length, label=None, loc=(0.05, 0.05)):
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    x = x0 + loc[0] * (x1 - x0); y = y0 + loc[1] * (y1 - y0)
    ax.plot([x, x + length], [y, y], color="k", lw=3, solid_capstyle="butt")
    ax.plot([x, x + length], [y, y], color="w", lw=1.2, solid_capstyle="butt")
    ax.text(x + length / 2, y + 0.02 * (y1 - y0), label or f"{length:g} m", ha="center", va="bottom",
            fontsize=8, bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))


def clean(ax):
    ax.set_xticks([]); ax.set_yticks([])


def save(fig, name):
    fig.savefig(OUT / name, dpi=110)
    plt.close(fig)
    print("wrote", OUT / name)


def utm_tf():
    s = osr.SpatialReference(); s.ImportFromEPSG(4326); s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    t = osr.SpatialReference(); t.ImportFromEPSG(32613)
    return osr.CoordinateTransformation(s, t)


TF = utm_tf()

# transect: through the site centre, along the flight direction (bearing 130 deg), +-500 m
c = TF.TransformPoint(-105.668673, 41.274962)[:2]
b = np.radians(130)
T0 = (c[0] - 480 * np.sin(b), c[1] - 480 * np.cos(b))
T1 = (c[0] + 480 * np.sin(b), c[1] + 480 * np.cos(b))
# detail windows
DETAIL = (444000, 4569500, 444060, 4569560)          # 60 m: two-track + drainage
VEGWIN = (443960, 4569400, 444060, 4569500)          # 100 m vegetation test area
BAND_A = (444020, 4569640, 444090, 4569710)          # artifact band

# ---------------------------------------------------------------- 1 site overview
def fig_overview():
    rgb, ext = ortho_rgb(width=1600)
    rows = list(csv.DictReader(open(INV)))
    pts = np.array([TF.TransformPoint(float(r["lon"]), float(r["lat"]))[:2] for r in rows])
    files = [r["file"] for r in rows]
    num = np.array([int(f[4:8]) for f in files])
    flight = np.where(num <= 637, 1, np.where(num <= 796, 2, 3))
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.imshow(rgb, extent=ext)
    for f, col in zip((1, 2, 3), ("#e41a1c", "#377eb8", "#ff7f00")):
        m = flight == f
        ax.plot(pts[m, 0], pts[m, 1], "-", color=col, lw=0.6, alpha=0.8)
        ax.scatter(pts[m, 0], pts[m, 1], s=5, color=col, label=f"flight {f} ({m.sum()} photos)", zorder=3)
    ax.plot([T0[0], T1[0]], [T0[1], T1[1]], "k--", lw=1.2)
    ax.annotate("profile A→B", xy=T1, xytext=(T1[0] - 120, T1[1] - 60), fontsize=8)
    ax.text(*T0, " A", fontsize=10, weight="bold"); ax.text(*T1, " B", fontsize=10, weight="bold")
    for (x0, y0, x1, y1), lab in [(DETAIL, "detail 1"), (VEGWIN, "veg test"), (BAND_A, "artifact A")]:
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="yellow", lw=1.2))
        ax.text(x1 + 5, y1, lab, color="yellow", fontsize=8, weight="bold",
                bbox=dict(fc="black", alpha=0.4, ec="none", pad=1))
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlabel("Easting (m, UTM 13N)"); ax.set_ylabel("Northing (m)")
    ax.ticklabel_format(useOffset=False, style="plain")
    scalebar(ax, 200)
    ax.set_title("Orthophoto (2 cm) with camera positions, profile line and example windows")
    save(fig, "01_overview.png")


# ---------------------------------------------------------------- 2 vertical check vs USGS 3DEP
def fig_doming():
    raw, ext = read(DTM_RAW, res=4)
    usgs, _ = read(USGS, res=4)
    diff, _ = read(DIFF, res=4)
    resid, _ = read(RESID, res=4)
    usgs[np.isnan(raw)] = np.nan
    fig, axs = plt.subplots(1, 4, figsize=(16, 4.2))
    for ax, a, t, cm, vmin, vmax in [
        (axs[0], raw, "Drone DTM, raw (ODM)", "terrain", None, None),
        (axs[1], usgs, "USGS 3DEP lidar DEM (NAVD88)", "terrain", None, None),
        (axs[2], diff, "Drone − 3DEP (m): offset + bowl", "RdBu_r", np.nanpercentile(diff, 1), np.nanpercentile(diff, 99)),
        (axs[3], resid, "After removing smooth trend (m)", "RdBu_r", -0.5, 0.5)]:
        im = ax.imshow(a, extent=ext, cmap=cm, vmin=vmin, vmax=vmax)
        plt.colorbar(im, ax=ax, shrink=0.75, label="m")
        ax.set_title(t); clean(ax)
    stats = json.load(open(P / "reference/trend_fit.json"))
    r = stats["residual_after_fit"]
    fig.suptitle(f"Vertical check against USGS 3DEP: raw mean offset {stats['raw_diff']['mean']:.1f} m, "
                 f"bowl range {stats['trend_range_m']:.1f} m → after correction RMSE {r['rmse']*100:.0f} cm "
                 f"(90 % within {r['p05']:+.2f} … {r['p95']:+.2f} m)", y=0.93)
    save(fig, "02_vertical_check.png")


# ---------------------------------------------------------------- 3 profile
def sample_line(path, p0, p1, step):
    ds = gdal.Open(str(path)); gt = ds.GetGeoTransform(); b = ds.GetRasterBand(1); nd = b.GetNoDataValue()
    L = np.hypot(p1[0] - p0[0], p1[1] - p0[1]); d = np.arange(0, L, step)
    xs = p0[0] + (p1[0] - p0[0]) * d / L; ys = p0[1] + (p1[1] - p0[1]) * d / L
    out = []
    for x, y in zip(xs, ys):
        px, py = int((x - gt[0]) / gt[1]), int((y - gt[3]) / gt[5])
        if 0 <= px < ds.RasterXSize and 0 <= py < ds.RasterYSize:
            v = float(b.ReadAsArray(px, py, 1, 1)[0, 0])
            out.append(np.nan if v == nd else v)
        else:
            out.append(np.nan)
    return d, np.array(out)


def fig_profile():
    d, raw = sample_line(DTM_RAW, T0, T1, 1.0)
    _, dtm = sample_line(DTM, T0, T1, 1.0)
    _, usgs = sample_line(USGS, T0, T1, 1.0)
    fig, axs = plt.subplots(2, 1, figsize=(11, 7))
    ax = axs[0]
    ax.plot(d, usgs, color="k", lw=2, label="USGS 3DEP lidar")
    ax.plot(d, dtm, color="tab:green", lw=1, label="Drone DTM, corrected (NAVD88)")
    ax2 = ax.twinx()
    ax2.plot(d, raw, color="tab:red", lw=1, ls="--", label="Drone DTM, raw (right axis)")
    ax2.set_ylabel("raw ODM elevation (m)", color="tab:red")
    ax.set_ylabel("elevation (m, NAVD88)"); ax.set_xlabel("distance along profile A→B (m)")
    ax.set_title("Profile A→B (960 m): raw DTM is bowl-shaped; corrected DTM follows the lidar")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", fontsize=8)
    # zoom: 40 m, at 5 cm sampling
    s0 = 440
    p0 = (T0[0] + (T1[0] - T0[0]) * s0 / 960, T0[1] + (T1[1] - T0[1]) * s0 / 960)
    p1 = (T0[0] + (T1[0] - T0[0]) * (s0 + 40) / 960, T0[1] + (T1[1] - T0[1]) * (s0 + 40) / 960)
    dz, dsm = sample_line(DSM, p0, p1, 0.05)
    _, dtz = sample_line(DTM, p0, p1, 0.05)
    _, fine = sample_line(P / "corrected/dtm_fine_10cm_navd88.tif", p0, p1, 0.05)
    ax = axs[1]
    ax.fill_between(dz + s0, fine, dsm, where=dsm > fine, color="tab:green", alpha=0.35, label="DSM above fine DTM (vegetation / noise)")
    ax.plot(dz + s0, dsm, color="tab:brown", lw=0.8, label="DSM (surface, 5 cm)")
    ax.plot(dz + s0, dtz, color="tab:blue", lw=0.8, ls="--", label="ODM DTM (default ground filter)")
    ax.plot(dz + s0, fine, color="k", lw=0.8, label="fine DTM (vegetation_chm.sh)")
    ax.set_xlabel("distance along profile (m)"); ax.set_ylabel("elevation (m)")
    ax.set_title("Zoom: 40 m of the same profile. Plant clumps and microrelief are a few cm to ~20 cm")
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    save(fig, "03_profile.png")


# ---------------------------------------------------------------- 4 terrain products
def fig_terrain():
    dtm, ext = read(DTM, res=2)
    hs = hillshade(dtm, 2, exag=3)
    fig, axs = plt.subplots(1, 2, figsize=(15, 6))
    ax = axs[0]
    norm = Normalize(np.nanpercentile(dtm, 1), np.nanpercentile(dtm, 99))
    col = plt.cm.terrain(norm(dtm))[..., :3]
    blend = col * (0.55 + 0.45 * hs[..., None])
    blend[np.isnan(dtm)] = 1
    ax.imshow(blend, extent=ext)
    sm = plt.cm.ScalarMappable(norm=norm, cmap="terrain"); plt.colorbar(sm, ax=ax, shrink=0.8, label="elevation (m, NAVD88)")
    # contours every 0.5 m, generated with GDAL from the 2 m view (smoothed DTM)
    from osgeo import ogr
    mem = gdal.GetDriverByName("MEM").Create("", dtm.shape[1], dtm.shape[0], 1, gdal.GDT_Float32)
    mem.SetGeoTransform((ext[0], 2, 0, ext[3], 0, -2))
    mb = mem.GetRasterBand(1); mb.SetNoDataValue(-9999); mb.WriteArray(np.where(np.isfinite(dtm), dtm, -9999))
    vds = ogr.GetDriverByName("Memory").CreateDataSource("c")
    lyr = vds.CreateLayer("c"); lyr.CreateField(ogr.FieldDefn("z", ogr.OFTReal))
    gdal.ContourGenerate(mb, 0.5, 0, [], 1, -9999, lyr, 0, 0)
    for feat in lyr:
        g = feat.GetGeometryRef(); zv = feat.GetField("z")
        parts = [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())] if g.GetGeometryCount() else [g]
        for p in parts:
            xy = np.array(p.GetPoints() or [])
            if len(xy) > 3:
                ax.plot(xy[:, 0], xy[:, 1], color="k", lw=0.6 if zv % 1 == 0 else 0.3, alpha=0.6)
                if zv % 1 == 0 and len(xy) > 60:
                    m = len(xy) // 2
                    ax.text(xy[m, 0], xy[m, 1], f"{zv:.0f}", fontsize=6,
                            bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.5))
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); clean(ax); scalebar(ax, 200)
    ax.set_title("Corrected DTM (NAVD88): relief + hillshade + 0.5 m contours")
    ax = axs[1]
    sl, ext2 = read(SLOPE, res=2)
    im = ax.imshow(sl, extent=ext2, cmap="magma_r", vmin=0, vmax=8)
    plt.colorbar(im, ax=ax, shrink=0.8, label="slope (degrees)")
    clean(ax); scalebar(ax, 200)
    ins = ax.inset_axes([0.62, 0.05, 0.35, 0.28])
    v = sl[np.isfinite(sl)]
    ins.hist(v, bins=60, range=(0, 8), color="0.3"); ins.set_title("slope histogram", fontsize=7)
    ins.tick_params(labelsize=6); ins.set_yticks([])
    ax.set_title(f"Terrain slope (1 m DTM): median {np.median(v):.1f}°, 95 % < {np.percentile(v, 95):.1f}°")
    save(fig, "04_terrain.png")


# ---------------------------------------------------------------- 5 DSM / DTM / CHM detail
def fig_detail():
    rgb, ext = ortho_rgb(DETAIL, width=600)
    dsm, e2 = read(DSM, DETAIL, res=0.05)
    dtm, _ = read(DTM, DETAIL, res=0.05)
    fine, _ = read(P / "corrected/dtm_fine_10cm_navd88.tif", DETAIL, res=0.05)
    chm, _ = read(CHM_VEG, DETAIL, res=0.1, alg="max")
    fig, axs = plt.subplots(1, 4, figsize=(17, 4.5))
    axs[0].imshow(rgb, extent=ext); axs[0].set_title("Orthophoto")
    axs[1].imshow(hillshade(dsm, 0.05, 2), cmap="gray", extent=e2); axs[1].set_title("DSM hillshade (surface incl. plants)")
    axs[2].imshow(hillshade(fine, 0.05, 2), cmap="gray", extent=e2); axs[2].set_title("Fine DTM hillshade (plants removed)")
    im = axs[3].imshow(chm, cmap="YlGn", vmin=0, vmax=0.3, extent=e2)
    plt.colorbar(im, ax=axs[3], shrink=0.8, label="height above ground (m)")
    axs[3].set_title("Vegetation height (max HAG, 10 cm)")
    for ax in axs:
        clean(ax); scalebar(ax, 10)
    fig.suptitle("Detail 1 (60 × 60 m): two-track road, incised drainage and bunchgrass clumps", y=1.02)
    save(fig, "05_detail_dsm_dtm_chm.png")


# ---------------------------------------------------------------- 6 vegetation
def fig_vegetation():
    cov, ext = read(COVER, res=2)
    fig, axs = plt.subplots(1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [1.6, 1]})
    ax = axs[0]
    im = ax.imshow(cov * 100, extent=ext, cmap="YlGn", vmin=0, vmax=40)
    plt.colorbar(im, ax=ax, shrink=0.8, label="% of area with vegetation ≥ 10 cm")
    ax.add_patch(plt.Rectangle(BAND_A[:2], BAND_A[2] - BAND_A[0], BAND_A[3] - BAND_A[1], fill=False, ec="red", lw=1.2))
    ax.text(BAND_A[2] + 5, BAND_A[3], "artifact band A", color="red", fontsize=8)
    ax.add_patch(plt.Rectangle(VEGWIN[:2], VEGWIN[2] - VEGWIN[0], VEGWIN[3] - VEGWIN[1], fill=False, ec="blue", lw=1.2))
    ax.text(VEGWIN[2] + 5, VEGWIN[1], "veg test", color="blue", fontsize=8)
    clean(ax); scalebar(ax, 200)
    ax.set_title("Vegetation cover (≥ 10 cm), 2 m view. Straight bands are artifacts")
    # right: zoom on veg test window, ortho vs mask overlay
    rgb, e2 = ortho_rgb(VEGWIN, width=700)
    mk, e3 = read(MASK, VEGWIN, res=0.1, alg="max")
    ax = axs[1]
    ax.imshow(rgb, extent=e2)
    ov = np.zeros(mk.shape + (4,)); ov[mk == 1] = (0.0, 0.9, 0.0, 0.85)
    ax.imshow(ov, extent=e3)
    clean(ax); scalebar(ax, 20)
    ax.set_title("Veg test window (100 m): orthophoto + vegetation ≥ 10 cm (green)")
    save(fig, "06_vegetation.png")


# ---------------------------------------------------------------- 7 point cloud cross-sections
def fig_sections():
    fig, axs = plt.subplots(2, 1, figsize=(12, 6.5))
    for ax, name, title in [
        (axs[0], "veg", "Real vegetation: 30 m × 0.4 m slice of points (veg test area)"),
        (axs[1], "band", "Artifact band A: 30 m × 0.4 m slice. Two layers ~10 cm apart (ghost surface)")]:
        rows = list(csv.DictReader(open(P / f"vegetation/sections/{name}.csv")))
        x = np.array([float(r["X"]) for r in rows]); z = np.array([float(r["Z"]) for r in rows])
        cl = np.array([float(r["Classification"]) for r in rows])
        x -= x.min(); z -= np.percentile(z[cl == 2], 5)
        ax.scatter(x[cl == 2], z[cl == 2], s=3, c="saddlebrown", label="ground (class 2)")
        ax.scatter(x[cl != 2], z[cl != 2], s=3, c="green", label="above ground (class 1)")
        ax.set_ylim(-0.15, max(0.45, np.percentile(z, 99.8) + 0.05))
        ax.set_ylabel("height (m, relative)"); ax.set_title(title); ax.legend(fontsize=8, loc="upper right")
        ax.grid(alpha=0.3)
    axs[1].set_xlabel("distance along slice (m)")
    fig.tight_layout()
    save(fig, "07_point_sections.png")


# ---------------------------------------------------------------- 8 3D perspective
def fig_3d():
    win = (443750, 4569330, 444200, 4569680)
    z, ext = read(DTM, win, res=4)
    rgb, _ = ortho_rgb(win, width=z.shape[1])
    n0, n1 = min(rgb.shape[0], z.shape[0]), min(rgb.shape[1], z.shape[1])
    rgb, z = rgb[:n0, :n1], z[:n0, :n1]
    rgb = np.clip(rgb * (0.55 + 0.6 * hillshade(z, 4, 20)[..., None]), 0, 1)
    X, Y = np.meshgrid(np.linspace(0, ext[1] - ext[0], z.shape[1]), np.linspace(ext[3] - ext[2], 0, z.shape[0]))
    fig = plt.figure(figsize=(11, 7))
    ax = fig.add_subplot(projection="3d")
    zz = np.where(np.isfinite(z), z, np.nanmin(z))
    ax.plot_surface(X, Y, zz, facecolors=rgb, rstride=1, cstride=1, linewidth=0, antialiased=False, shade=False)
    ax.set_box_aspect((1, (ext[3] - ext[2]) / (ext[1] - ext[0]), 0.25))
    ax.view_init(elev=35, azim=-60)
    ax.set_xlabel("m"); ax.set_ylabel("m"); ax.set_zlabel("elevation (m)")
    ax.set_title("3D view: corrected DTM draped with the orthophoto (450 × 350 m, strong vertical exaggeration)")
    save(fig, "08_3d_view.png")


for f in (fig_overview, fig_doming, fig_profile, fig_terrain, fig_detail, fig_vegetation, fig_sections, fig_3d):
    try:
        f()
    except Exception as e:  # keep going so one failure doesn't block the rest
        print(f"FAILED {f.__name__}: {e!r}")
