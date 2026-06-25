import geopandas as gpd
import rasterio as rio
from pathlib import Path
import pandas as pd

# 1 load s2 raster image
fp = Path("/home/feds/Data/S2_file.tif")
scale_val = 10_000

with rio.open(fp) as dataset:
    r = b4 = dataset.read(1) /scale_val# r
    g = b3 = dataset.read(2) /scale_val# g
    b = b2 = dataset.read(3) /scale_val# b
    nir = b8 = dataset.read(4) /scale_val# nir
    redge = b5 = dataset.read(5) /scale_val

    # 1.1 calc indices for selected pixels
    ndvi = (b4 - b8) / (b4 + b8 + 1e-8) # avoid division by zero
    evi = 2.5 * (nir - r) / (nir + 6 * r - 7.5 * b + 1)
    mcari = ((redge - r) - 0.2 * (redge - g)) * (redge / r) # (Modified Chlorophyll Absorption in Reflectance Index) 
    # todo add biomass estimate index

    # 1.2 add arrays back to tif, or keep if they have spatial/pixel info

# 2 load data from Daniel (point/pixel id?) 
# file format gpkg or csv?
df_fp = Path("./data/daniel_file.gpkg")
df = gpd.read_file(df_fp)
# or 
#df = pd.read_csv(df_fp)
# 2.1.1 transform df to gdf via gpd.points_from_xy(df.Long, df.Lat)
# 2.1.2 or find a way to join

# 3 extract s2 pixels corresponding to sample points

# 4 export as pd dataframe for easy visualization
df_joined = pd.DataFrame()
df_joined.to_parquet("./data/processed/df_combined.parquet")
df_joined.to_csv("./data/processed/df_combined.csv")