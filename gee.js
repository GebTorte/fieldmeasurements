// =========================================================================
// 1. DATA SETUP (Group members change the parameters here)
// =========================================================================

/////////////////////////////////////////////////////////////////////////////////////
// Draw polygon from Imports , scene will be also cutted due to this AOI
var myField = geometry; 

// Enter the target fieldwork date here (YYYY-MM-DD)
var targetDateStr = '2026-06-23'; 

/////////////////////////////////////////////////////////////////////////////////////
// Maximum allowable cloud cover for the scene (%)
var maxCloudPercent = 50; 

// =========================================================================
// 2. CLOUD MASKING FUNCTION
// =========================================================================
function maskS2clouds(image) {
  var qa = image.select('QA60');
  var cloudBitMask = 1 << 10;
  var cirrusBitMask = 1 << 11;
  var mask = qa.bitwiseAnd(cloudBitMask).eq(0)
      .and(qa.bitwiseAnd(cirrusBitMask).eq(0));
  
  return image.updateMask(mask).divide(10000)
              .copyProperties(image, ["system:time_start", "CLOUDY_PIXEL_PERCENTAGE"]);
}

// =========================================================================
// 3. CLOSEST IMAGE SEARCH
// =========================================================================
var targetDate = ee.Date(targetDateStr);
var startSearch = targetDate.advance(-5, 'day'); // Search window: +/- 5 days around fieldwork
var endSearch = targetDate.advance(5, 'day');

var s2Collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(myField)
    .filterDate(startSearch, endSearch)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', maxCloudPercent))
    .map(maskS2clouds);

// Calculate the time difference and select the closest image
var withTimeDiff = s2Collection.map(function(img) {
  var imgDate = ee.Date(img.get('system:time_start'));
  var diff = imgDate.difference(targetDate, 'day').abs();
  return img.set('time_dist', diff);
});

var bestImage = withTimeDiff.sort('time_dist').first();

//// Resample B5 from 20m to 10m using bilinear interpolation
var b5_10m = bestImage.select('B5')
    .resample('bilinear')
    .reproject({
      crs: bestImage.select('B2').projection().crs(),
      scale: 10
    });
    
// Correctly select 10m bands and attach the upsampled 10m B5 band
var exportImage = bestImage.select(['B4', 'B3', 'B2', 'B8']).addBands(b5_10m);

// =========================================================================
// 4. PRINT INFORMATION TO THE CONSOLE
// =========================================================================
print("=== IMAGE INFORMATION FOR QGIS ===");
print("Requested fieldwork date:", targetDateStr);
print("Satellite image date found:", ee.Date(bestImage.get('system:time_start')).format('YYYY-MM-dd HH:mm'));
print("SCENE CLOUD COVER (%):", bestImage.get('CLOUDY_PIXEL_PERCENTAGE'));
print("Days apart (Fieldwork vs Satellite):", bestImage.get('time_dist'));

// Map visualization in GEE for verification
Map.centerObject(myField, 15);
Map.addLayer(myField, {color: 'red'}, 'Our Field Polygon');
Map.addLayer(bestImage, {bands: ['B4', 'B3', 'B2'], min: 0, max: 0.3}, 'Sentinel-2 Image');

// =========================================================================
// 5. PREPARE DOWNLOAD FOR QGIS
// =========================================================================

// Safely get the geometry to clip the raster
var exportRegion = myField.geometry ? myField.geometry() : myField;

// Export directly to Google Drive (will appear in the Tasks tab on the top-right)
Export.image.toDrive({
  image: exportImage,
  description: 'Sentinel2_' + targetDateStr,
  scale: 10, // Keep the original 10-meter spatial resolution
  region: exportRegion, // Automatically clips the image to your field boundary
  fileFormat: 'GeoTIFF'
});