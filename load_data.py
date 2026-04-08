"""Load Chicago zoning CSV into PostGIS database."""

import geopandas as gpd
import pandas as pd
from shapely import wkt
from sqlalchemy import create_engine

CSV_PATH = "../Boundaries_-_Zoning_Districts_(current)_20260407.csv"
DB_URL = "postgresql://pgwhalen@localhost:5432/urbanism"

def main():
    print("Reading CSV...")
    df = pd.read_csv(CSV_PATH)
    print(f"  {len(df)} rows")

    print("Parsing geometries...")
    df["geometry"] = df["the_geom"].apply(wkt.loads)
    # Source data is in WGS84 (lon/lat); reproject to EPSG:3435 (IL State Plane East, US feet)
    gdf = gpd.GeoDataFrame(df.drop(columns=["the_geom"]), geometry="geometry", crs="EPSG:4326")
    gdf = gdf.to_crs(epsg=3435)

    # Clean column names to lowercase for postgres
    gdf.columns = [c.lower() for c in gdf.columns]

    print("Writing to PostGIS...")
    engine = create_engine(DB_URL)
    gdf.to_postgis("zoning_districts", engine, if_exists="replace", index=False)

    print("Done.")

if __name__ == "__main__":
    main()
