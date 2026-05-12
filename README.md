## requirements.txt:
geopandas 
rasterio
numpy 
scipy 
pykrige 
matplotlib

## usage
python interpolate_classes.py \
    --gpkg  samples.gpkg \
    --dem   dem.tif \
    --class-field class \   # column name in your .gpkg
    --method both \          # "kriging", "nn", or "both"
    --variogram spherical \  # spherical | exponential | gaussian | linear
    --out-dir ./output
