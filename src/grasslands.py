import geopandas as gpd
import rasterio as rio
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date


def calc_indices_for_sample(lst: list, e:float = 1e-8):
    """
    samples in order of bands
    r     - 1
    g     - 2
    b     - 3
    nir   - 4
    redge - 5
    """
    r, g, b, nir, redge = lst
    # 1.1 calc indices for selected pixels
    ndvi = (nir - r) / (nir + r + e)  # avoid division by zero
    evi = 2.5 * (nir - r) / (nir + 6 * r - 7.5 * b + 1)
    mcari = ((redge - r) - 0.2 * (redge - g)) * (
        redge / (r + e)
    )  # (Modified Chlorophyll Absorption in Reflectance Index)

    # todo add biomass estimate index

    return {"ndvi": ndvi, "evi": evi, "mcari": mcari}


# 2 load data from Daniel (point/pixel id?)
# file format gpkg or csv?
# df_fp = Path("./data/wrzburg_s2_grid_centroid.gpkg")
df_fp = Path("./data/wrzburg__s2_grid.gpkg")
df = gpd.read_file(df_fp).dropna()
df2 = pd.DataFrame(df)  # convert to pd for joining

# fix csv by opening in libre office excel and exporting as csv again
csv_fp = Path("./data/Grassland_fixed.csv")
csv_df = pd.read_csv(csv_fp)[1:]  # skip nan row
csv_df["Plot_ID"] = csv_df["Plot ID"]  # rename for join

rsuffix = "_csv"
lsuffix = "_grid"
df_joined = df2.join(csv_df, on="Plot_ID", lsuffix=lsuffix, rsuffix=rsuffix)
# or
# df = pd.read_csv(df_fp)
# 2.1.1 transform df to gdf via gpd.points_from_xy(df.Long, df.Lat)
# 2.1.2 or find a way to (inner) join

# view sorted
# df_joined.sort_values("Plot_ID")

# optionally save
# df_joined.to_parquet("./data/processed/df_combined.parquet")
# df_joined.to_csv("./data/processed/df_combined.csv")

################################################
# load s2 raster image
# image from 2026-06-22 10:36
# > gdal_translate -of GPKG <input-file>.tif <output-file>.gpkg # <-- only works for up to 4 bands...
sat_date = date(2026, 6, 22)

sample_dates = [date(2026, 6, 23), date(2026, 6, 24)]
fp = Path("/home/feds/projects/fieldmeasurements/data/s2/Sentinel2_2026-06-23.tif")
# scale_val = 10_000 # todo adapt L2A refl scale to c1,c2 formula in https://sentiwiki.copernicus.eu/web/s2-products#:~:text=L2A%5FSRi%20%3D%20%28L2A%5FDNi%20%2B%20BOA%5FADD%5FOFFSETi%29%20%2F%20QUANTIFICATION%5FVALUE

# back to gdf
gdf = gpd.GeoDataFrame(df_joined, geometry="geometry")

#sample_dates = [sampling_date] # todo fix this with a mapping of sampling_date: satellite_date, to avoid having multiple of the same sat imgs
    # or select nearest sat img for sampling
#dt_sample_dates = [pd.to_datetime(d, format="%Y-%m-%d")  for d in sample_dates] # convert for comparison
# back to gdf
#gdf = gpd.GeoDataFrame(df, geometry="geometry")

# filter for date-relevant plot ids
gdf = gdf[gdf[f"Plot_ID{rsuffix}"].isin(range(132, 142))]
# or filter for dates (first clean csv dates...)
#gdf["Date"] = pd.to_datetime(gdf["Date"], format="%d.%m.%Y")
#gdf = gdf[gdf["Date"].isin(sample_dates)]

with rio.open(fp) as src:
    # unify crs
    if gdf.crs != src.crs:
        gdf = gdf.to_crs(src.crs)

    # r = b4 = src.read(1).astype('float64') #/scale_val# r
    # g = b3 = src.read(2).astype('float64') #/scale_val# g
    # b = b2 = src.read(3).astype('float64') #/scale_val# b
    # nir = b8 = src.read(4).astype('float64') #/scale_val# nir
    # redge = b5 = src.read(5).astype('float64') #/scale_val

    # preview ndvi
    # plt.imshow(ndvi, "Greens")
    # plt.show()

    # Prepare a list of (x, y) coordinates
    # adapted to gdf.geometry.centroid.xy
    coords = [(x, y) for x, y in zip(gdf.geometry.centroid.x, gdf.geometry.centroid.y)]

    # Sample the raster at all points
    # - extract values for centroid points
    samples = list(
        src.sample(coords)
    )  # assuming sample returns band samples in order of bands

    results = []
    for s in samples:
        results.append(calc_indices_for_sample(s))

    gdf["ndvi"] = [r["ndvi"] for r in results]
    gdf["evi"] = [r["evi"] for r in results]
    gdf["mcari"] = [r["mcari"] for r in results]

# export to file
gdf.to_file(f"./data/processed/results_{sat_date}_small.gpkg")

gdf.plot(column="ndvi")
