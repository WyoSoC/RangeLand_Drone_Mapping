#!/usr/bin/env python3
"""Check and correct drone DEMs against USGS 3DEP (lidar) elevation.

Without GCPs/RTK, ODM elevations have (1) a constant vertical offset from the drone's
GPS height reference and (2) a smooth, large-scale "doming"/bowl distortion from
structure-from-motion with nadir-only images. This script measures both against the
USGS 3DEP DEM and removes them by fitting a low-order 2D polynomial to (drone - 3DEP).
The result is in 3DEP heights (NAVD88, metres).

Local detail (< tens of metres: trails, plant clumps, vegetation height) is not changed.
Only the smooth trend is removed.

Needs Python with GDAL bindings + numpy, e.g. QGIS's bundled Python:
    /Applications/QGIS-*.app/Contents/MacOS/python scripts/correct_dem_3dep.py processing/2026-05-21_Map

Usage:
    correct_dem_3dep.py <project_dir> [--order 2] [--res 2]

Outputs:
    <project>/reference/usgs_3dep_2m.tif        3DEP DEM for the site (downloaded if missing)
    <project>/reference/diff_drone_minus_3dep.tif   raw difference (2 m)
    <project>/reference/residual_after_fit.tif      difference after removing the fitted trend
    <project>/reference/trend_fit.json              polynomial coefficients + accuracy statistics
    <project>/corrected/{dsm,dtm,dtm_fine_10cm}_navd88.tif   corrected DEMs (COG)
"""
import argparse
import glob
import json
import os
import sys
import urllib.request
from pathlib import Path

# QGIS's bundled Python doesn't set PROJ_DATA when run outside QGIS: find proj.db.
if not os.environ.get("PROJ_DATA"):
    exe = Path(sys.executable).resolve()
    for cand in glob.glob(str(exe.parents[1] / "Resources" / "qgis" / "proj")) + \
            ["/opt/homebrew/share/proj", "/usr/local/share/proj", "/usr/share/proj"]:
        if Path(cand, "proj.db").exists():
            os.environ["PROJ_DATA"] = cand
            break

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
EXPORT_URL = ("https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
              "?bbox={xmin},{ymin},{xmax},{ymax}&bboxSR={epsg}&imageSR={epsg}&size={w},{h}"
              "&format=tiff&pixelType=F32&interpolation=RSP_BilinearInterpolation&f=image")


def epsg_of(ds):
    srs = ds.GetSpatialRef()
    srs.AutoIdentifyEPSG()
    return int(srs.GetAuthorityCode(None))


def get_3dep(ref_path: Path, like: Path, res: float):
    if ref_path.exists():
        return
    ds = gdal.Open(str(like))
    gt, w, h = ds.GetGeoTransform(), ds.RasterXSize, ds.RasterYSize
    xmin, ymax = gt[0], gt[3]
    xmax, ymin = xmin + gt[1] * w, ymax + gt[5] * h
    url = EXPORT_URL.format(xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax, epsg=epsg_of(ds),
                            w=int(round((xmax - xmin) / res)), h=int(round((ymax - ymin) / res)))
    print(f"Downloading USGS 3DEP ({res} m) ...")
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, ref_path)


def design(x, y, order):
    cols = [x ** i * y ** j for i in range(order + 1) for j in range(order + 1 - i)]
    return np.stack(cols, axis=-1)


def poly_eval(coef, x, y, order):
    out = np.zeros(np.broadcast(x, y).shape, dtype=np.float64)
    k = 0
    for i in range(order + 1):
        for j in range(order + 1 - i):
            out += coef[k] * x ** i * y ** j
            k += 1
    return out


def write_like(path, arr, ref_ds, nodata=-9999.0):
    drv = gdal.GetDriverByName("GTiff")
    out = drv.Create(str(path), arr.shape[1], arr.shape[0], 1, gdal.GDT_Float32,
                     ["COMPRESS=DEFLATE", "PREDICTOR=3"])
    out.SetGeoTransform(ref_ds.GetGeoTransform())
    out.SetProjection(ref_ds.GetProjection())
    b = out.GetRasterBand(1)
    b.SetNoDataValue(nodata)
    b.WriteArray(np.where(np.isfinite(arr), arr, nodata).astype(np.float32))
    out = None


def correct(src: Path, dst: Path, coef, order, x0, y0, scale):
    """Subtract fitted trend from a (large) DEM block by block, write COG."""
    ds = gdal.Open(str(src))
    band = ds.GetRasterBand(1)
    nd = band.GetNoDataValue()
    gt = ds.GetGeoTransform()
    tmp = dst.with_suffix(".tmp.tif")
    drv = gdal.GetDriverByName("GTiff")
    out = drv.Create(str(tmp), ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Float32,
                     ["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES", "BIGTIFF=IF_SAFER"])
    out.SetGeoTransform(gt)
    out.SetProjection(ds.GetProjection())
    ob = out.GetRasterBand(1)
    ob.SetNoDataValue(-9999.0)
    step = 1024
    xs = gt[0] + (np.arange(ds.RasterXSize) + 0.5) * gt[1]
    for r0 in range(0, ds.RasterYSize, step):
        n = min(step, ds.RasterYSize - r0)
        a = band.ReadAsArray(0, r0, ds.RasterXSize, n).astype(np.float64)
        ys = gt[3] + (np.arange(r0, r0 + n) + 0.5) * gt[5]
        X, Y = np.meshgrid((xs - x0) / scale, (ys - y0) / scale)
        valid = a != nd if nd is not None else np.isfinite(a)
        a = np.where(valid, a - poly_eval(coef, X, Y, order), -9999.0)
        ob.WriteArray(a.astype(np.float32), 0, r0)
    out = None
    gdal.Translate(str(dst), str(tmp), format="COG",
                   creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=3", "BIGTIFF=IF_SAFER"])
    tmp.unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", type=Path)
    ap.add_argument("--order", type=int, default=2, help="polynomial order of trend (default 2)")
    ap.add_argument("--res", type=float, default=2.0, help="comparison grid (m), default 2")
    a = ap.parse_args()

    proj = a.project
    dtm = proj / "odm_dem" / "dtm.tif"
    ref = proj / "reference" / "usgs_3dep_2m.tif"
    get_3dep(ref, dtm, a.res)
    ref_ds = gdal.Open(str(ref))
    usgs = ref_ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    usgs[(usgs < -1000) | (usgs > 9000)] = np.nan

    # drone DTM averaged onto the 3DEP grid
    gt = ref_ds.GetGeoTransform()
    w, h = ref_ds.RasterXSize, ref_ds.RasterYSize
    warped = gdal.Warp("", str(dtm), format="MEM", outputBounds=(gt[0], gt[3] + gt[5] * h, gt[0] + gt[1] * w, gt[3]),
                       width=w, height=h, resampleAlg="average", dstNodata=np.nan)
    drone = warped.GetRasterBand(1).ReadAsArray().astype(np.float64)
    diff = drone - usgs

    xs = gt[0] + (np.arange(w) + 0.5) * gt[1]
    ys = gt[3] + (np.arange(h) + 0.5) * gt[5]
    X, Y = np.meshgrid(xs, ys)
    m = np.isfinite(diff)
    x0, y0 = X[m].mean(), Y[m].mean()
    scale = max(np.ptp(X[m]), np.ptp(Y[m])) / 2
    xn, yn = (X - x0) / scale, (Y - y0) / scale

    # robust least squares (drop > 3 sigma residuals, e.g. ponds, vehicles, edge noise)
    keep = m.copy()
    for _ in range(5):
        A = design(xn[keep], yn[keep], a.order)
        coef, *_ = np.linalg.lstsq(A, diff[keep], rcond=None)
        res = diff - poly_eval(coef, xn, yn, a.order)
        s = np.nanstd(res[keep])
        keep = m & (np.abs(res) < 3 * s)
    trend = poly_eval(coef, xn, yn, a.order)
    resid = diff - trend

    stats = {
        "reference": "USGS 3DEP (NAVD88, metres), elevation.nationalmap.gov",
        "comparison_grid_m": a.res,
        "order": a.order,
        "centre_xy": [x0, y0], "scale_m": scale, "coefficients": coef.tolist(),
        "n_cells": int(m.sum()),
        "raw_diff": {"mean": float(np.nanmean(diff)), "std": float(np.nanstd(diff)),
                     "min": float(np.nanmin(diff)), "max": float(np.nanmax(diff))},
        "trend_range_m": float(np.nanmax(np.where(m, trend, np.nan)) - np.nanmin(np.where(m, trend, np.nan))),
        "residual_after_fit": {"mean": float(np.nanmean(resid)), "std": float(np.nanstd(resid)),
                               "rmse": float(np.sqrt(np.nanmean(resid ** 2))),
                               "p05": float(np.nanpercentile(resid, 5)), "p95": float(np.nanpercentile(resid, 95))},
    }
    (proj / "reference").mkdir(exist_ok=True)
    write_like(proj / "reference" / "diff_drone_minus_3dep.tif", diff, ref_ds)
    write_like(proj / "reference" / "residual_after_fit.tif", resid, ref_ds)
    (proj / "reference" / "trend_fit.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps({k: v for k, v in stats.items() if k not in ("coefficients",)}, indent=2))

    outdir = proj / "corrected"
    outdir.mkdir(exist_ok=True)
    for src, name in [(proj / "odm_dem" / "dsm.tif", "dsm_navd88.tif"),
                      (proj / "odm_dem" / "dtm.tif", "dtm_navd88.tif"),
                      (proj / "vegetation" / "dtm_fine_10cm.tif", "dtm_fine_10cm_navd88.tif")]:
        if src.exists():
            print(f"Correcting {src.name} -> corrected/{name}")
            correct(src, outdir / name, coef, a.order, x0, y0, scale)
    print("Done.")


if __name__ == "__main__":
    sys.exit(main())
