"""
interpolate_classes.py
======================
Interpolate discrete class labels (0–7) from .gpkg point samples onto a
raster grid derived from a DEM, using:
  - Indicator Kriging  (statistically correct for categorical data)
  - Nearest-Neighbour  (simple, always preserves original class values)

Dependencies:
    pip install geopandas rasterio numpy scipy pykrige matplotlib

Usage:
    python interpolate_classes.py \
        --gpkg  samples.gpkg \
        --dem   dem.tif \
        --layer <layer_name>         # optional, defaults to first layer \
        --class-field <field_name>   # column holding class 0-7 (default: "class") \
        --method kriging|nn|both     # default: both \
        --out-dir ./output
"""

import argparse
import os
import sys
import warnings

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# Optional – kriging
try:
    from pykrige.ok import OrdinaryKriging
    PYKRIGE_AVAILABLE = True
except ImportError:
    PYKRIGE_AVAILABLE = False
    print("[WARNING] pykrige not found. Indicator Kriging will be skipped.")
    print("          Install with:  pip install pykrige")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_samples(gpkg_path: str, layer: str | None, class_field: str):
    """Load point samples from a GeoPackage."""
    layers = gpd.list_layers(gpkg_path)["name"].tolist()
    if layer is None:
        layer = layers[0]
        print(f"[INFO] Using layer: '{layer}'  (available: {layers})")
    elif layer not in layers:
        sys.exit(f"[ERROR] Layer '{layer}' not in {layers}")

    gdf = gpd.read_file(gpkg_path, layer=layer)

    if class_field not in gdf.columns:
        sys.exit(
            f"[ERROR] Field '{class_field}' not found.\n"
            f"        Available columns: {list(gdf.columns)}"
        )

    gdf = gdf[gdf.geometry.notna() & gdf.geometry.geom_type.eq("Point")].copy()
    gdf[class_field] = gdf[class_field].astype(int)
    print(f"[INFO] Loaded {len(gdf)} point samples, classes: {sorted(gdf[class_field].unique())}")
    return gdf, layer


def load_dem_grid(dem_path: str, gdf: gpd.GeoDataFrame):
    """
    Read the DEM, reproject samples to DEM CRS if needed, and return the
    grid arrays (X, Y meshgrid in the DEM's coordinate system).
    """
    with rasterio.open(dem_path) as src:
        dem_crs = src.crs
        transform = src.transform
        width, height = src.width, src.height
        bounds = src.bounds
        dem_data = src.read(1, masked=True)

    # Reproject samples to DEM CRS
    if gdf.crs is None:
        print("[WARNING] Sample layer has no CRS – assuming same as DEM.")
        gdf = gdf.set_crs(dem_crs)
    elif gdf.crs != dem_crs:
        print(f"[INFO] Reprojecting samples from {gdf.crs.to_epsg()} → {dem_crs.to_epsg()}")
        gdf = gdf.to_crs(dem_crs)

    # Build output grid (pixel-centre coordinates)
    xs = np.linspace(bounds.left  + transform.a / 2,
                     bounds.right - transform.a / 2, width)
    ys = np.linspace(bounds.top   + transform.e / 2,
                     bounds.bottom - transform.e / 2, height)   # top→bottom
    grid_x, grid_y = np.meshgrid(xs, ys)

    return gdf, dem_crs, transform, dem_data, grid_x, grid_y, bounds


def save_raster(array: np.ndarray, path: str, transform, crs, nodata=-1):
    """Write a 2-D integer array to a GeoTIFF."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with rasterio.open(
        path, "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        dtype="int16",
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="lzw",
    ) as dst:
        dst.write(array.astype("int16"), 1)
    print(f"[INFO] Saved raster → {path}")


def plot_result(array: np.ndarray, title: str, path: str, n_classes: int = 8):
    """Quick-look PNG with a discrete colormap."""
    cmap = plt.cm.get_cmap("tab10", n_classes)
    bounds_cb = np.arange(-0.5, n_classes + 0.5)
    norm = mcolors.BoundaryNorm(bounds_cb, cmap.N)

    fig, ax = plt.subplots(figsize=(8, 6), tight_layout=True)
    im = ax.imshow(array, cmap=cmap, norm=norm, interpolation="nearest")
    cbar = fig.colorbar(im, ax=ax, ticks=np.arange(n_classes))
    cbar.set_label("Class")
    ax.set_title(title)
    ax.axis("off")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"[INFO] Saved preview  → {path}")


# ---------------------------------------------------------------------------
# Nearest-Neighbour interpolation
# ---------------------------------------------------------------------------

def nearest_neighbour(sx, sy, classes, grid_x, grid_y):
    """Assign each grid cell the class of its nearest sample point."""
    print("[INFO] Running Nearest-Neighbour interpolation …")
    sample_pts = np.column_stack([sx, sy])
    grid_pts   = np.column_stack([grid_x.ravel(), grid_y.ravel()])

    tree = cKDTree(sample_pts)
    _, idx = tree.query(grid_pts, workers=-1)
    result = classes[idx].reshape(grid_x.shape)
    print("[INFO] Nearest-Neighbour done.")
    return result


# ---------------------------------------------------------------------------
# Indicator Kriging
# ---------------------------------------------------------------------------

def indicator_kriging(
    sx, sy, classes, grid_x, grid_y,
    unique_classes,
    variogram_model: str = "spherical",
    nlags: int = 12,
):
    """
    For each class k, binarise the samples (1 if class==k, else 0) and krige
    the probability surface.  The final class map is the argmax across all
    indicator surfaces.
    """
    if not PYKRIGE_AVAILABLE:
        print("[SKIP] pykrige unavailable – skipping Indicator Kriging.")
        return None

    print(f"[INFO] Running Indicator Kriging ({len(unique_classes)} classes, "
          f"variogram='{variogram_model}') …")

    h, w = grid_x.shape
    prob_stack = np.zeros((len(unique_classes), h, w), dtype=np.float32)

    gx_flat = grid_x.ravel()
    gy_flat = grid_y.ravel()

    for i, cls in enumerate(unique_classes):
        indicator = (classes == cls).astype(float)
        print(f"  [Kriging] Class {cls} ({indicator.sum():.0f} positive samples) …",
              end=" ", flush=True)

        # Suppress pykrige convergence warnings for brevity
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ok = OrdinaryKriging(
                sx, sy, indicator,
                variogram_model=variogram_model,
                nlags=nlags,
                verbose=False,
                enable_plotting=False,
            )
            z, _ = ok.execute("points", gx_flat, gy_flat)

        prob_stack[i] = np.clip(z, 0, 1).reshape(h, w)
        print("done")

    # Argmax → class with highest estimated probability
    result_idx = np.argmax(prob_stack, axis=0)
    result = unique_classes[result_idx]
    print("[INFO] Indicator Kriging done.")
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Interpolate discrete classes from point samples.")
    p.add_argument("--gpkg",        required=True,  help="Path to input GeoPackage")
    p.add_argument("--dem",         required=True,  help="Path to DEM GeoTIFF (sets grid extent/resolution)")
    p.add_argument("--layer",       default=None,   help="GeoPackage layer name (default: first layer)")
    p.add_argument("--class-field", default="class",help="Column name holding class values 0-7")
    p.add_argument("--method",      default="both", choices=["kriging", "nn", "both"])
    p.add_argument("--variogram",   default="spherical",
                   choices=["spherical", "exponential", "gaussian", "linear"],
                   help="Variogram model for Indicator Kriging")
    p.add_argument("--out-dir",     default="./output", help="Output directory")
    return p.parse_args()


def main():
    args = parse_args()

    # ── Load data ──────────────────────────────────────────────────────────
    gdf, layer_name = load_samples(args.gpkg, args.layer, args.class_field)
    gdf, dem_crs, transform, dem_data, grid_x, grid_y, bounds = load_dem_grid(
        args.dem, gdf
    )

    sx = gdf.geometry.x.values
    sy = gdf.geometry.y.values
    classes = gdf[args.class_field].values.astype(int)
    unique_classes = np.array(sorted(np.unique(classes)))

    os.makedirs(args.out_dir, exist_ok=True)

    # ── Nearest Neighbour ──────────────────────────────────────────────────
    if args.method in ("nn", "both"):
        nn_result = nearest_neighbour(sx, sy, classes, grid_x, grid_y)
        out_tif = os.path.join(args.out_dir, "classes_nn.tif")
        save_raster(nn_result, out_tif, transform, dem_crs)
        plot_result(
            nn_result,
            f"Nearest-Neighbour Classification\n({layer_name})",
            os.path.join(args.out_dir, "classes_nn.png"),
            n_classes=max(unique_classes) + 1,
        )

    # ── Indicator Kriging ──────────────────────────────────────────────────
    if args.method in ("kriging", "both"):
        ik_result = indicator_kriging(
            sx, sy, classes, grid_x, grid_y,
            unique_classes,
            variogram_model=args.variogram,
        )
        if ik_result is not None:
            out_tif = os.path.join(args.out_dir, "classes_indicator_kriging.tif")
            save_raster(ik_result, out_tif, transform, dem_crs)
            plot_result(
                ik_result,
                f"Indicator Kriging Classification\n({layer_name}, variogram={args.variogram})",
                os.path.join(args.out_dir, "classes_indicator_kriging.png"),
                n_classes=max(unique_classes) + 1,
            )

    print("\n[DONE] All outputs written to:", args.out_dir)


if __name__ == "__main__":
    main()
