import geopandas as gpd
import rasterio as rio
from pathlib import Path
import pandas as pd
import polars as pl
import matplotlib.pyplot as plt

# 1 load s2 raster image
fp = Path("/home/feds/projects/fieldmeasurements/data/s2/Sentinel2_2026-06-23.tif")
scale_val = 10_000 # todo adapt L2A refl scale to c1,c2 formula in https://sentiwiki.copernicus.eu/web/s2-products#:~:text=L2A%5FSRi%20%3D%20%28L2A%5FDNi%20%2B%20BOA%5FADD%5FOFFSETi%29%20%2F%20QUANTIFICATION%5FVALUE

with rio.open(fp) as dataset:
    r = b4 = dataset.read(1).astype('float64') /scale_val# r
    g = b3 = dataset.read(2).astype('float64') /scale_val# g
    b = b2 = dataset.read(3).astype('float64') /scale_val# b
    nir = b8 = dataset.read(4).astype('float64') /scale_val# nir
    redge = b5 = dataset.read(5).astype('float64') /scale_val

    # 1.1 calc indices for selected pixels
    ndvi = (b8 - b4) / (b8 + b4 + 1e-8) # avoid division by zero
    evi = 2.5 * (nir - r) / (nir + 6 * r - 7.5 * b + 1)
    mcari = ((redge - r) - 0.2 * (redge - g)) * (redge / r) # (Modified Chlorophyll Absorption in Reflectance Index) 
    # todo add biomass estimate index

    # 1.2 add arrays back to tif, or keep if they have spatial/pixel info

# preview ndvi
plt.imshow(ndvi, "Greens")
plt.show()

# 2 load data from Daniel (point/pixel id?) 
# file format gpkg or csv?
df_fp = Path("./data/wrzburg_s2_grid_centroid.gpkg")
df = gpd.read_file(df_fp).dropna()

# check where we are
df.plot()

# convert to pd
df2 = pd.DataFrame(df)

#df_aoi_bib = df[3:5]
#df_aoi_hoechberg = df[12:16]
#df_aoi_bib.plot()

# todo: assign pixel to measurement and id
csv_fp = Path("./data/Grassland_fixed.csv")
csv_df = pd.read_csv(csv_fp)[1:] # skip nan row
csv_df["Plot_ID"] = csv_df["Plot ID"]
df_joined = df2.join(csv_df, on="Plot_ID", lsuffix="_left", rsuffix="_right")
# or 
#df = pd.read_csv(df_fp)
# 2.1.1 transform df to gdf via gpd.points_from_xy(df.Long, df.Lat)
# 2.1.2 or find a way to (inner) join

df_joined.sort_values("Plot_ID")

# 3 extract s2 pixels corresponding to sample points

# 4 export as pd dataframe for easy visualization
df_joined = pd.DataFrame()
df_joined.to_parquet("./data/processed/df_combined.parquet")
df_joined.to_csv("./data/processed/df_combined.csv")