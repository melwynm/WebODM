ALTER USER postgres PASSWORD 'postgres';
CREATE DATABASE webodm_dev;
ALTER DATABASE webodm_dev SET postgis.gdal_enabled_drivers TO 'GTiff';
ALTER DATABASE webodm_dev SET postgis.enable_outdb_rasters TO True;
\connect webodm_dev
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
