"""Visualize Chicago zoning districts that benefit from single-stair ordinance."""

import geopandas as gpd
import folium
from sqlalchemy import create_engine

DB_URL = "postgresql://pgwhalen@localhost:5432/urbanism"
WARDS_GEOJSON = "Boundaries_-_Wards_(2023-)_20260407.geojson"

# Zones explicitly called out as high-benefit for single stair
HIGH_BENEFIT = {"B1-3", "C1-2", "RM-5"}

# Business/commercial zones with -3 or -5 suffix (medium benefit)
MEDIUM_BENEFIT = {
    "B1-5", "B2-3", "B2-5", "B3-3", "B3-5",
    "C1-3", "C1-5", "C2-3", "C2-5", "C3-3", "C3-5",
}

ALL_BENEFIT = HIGH_BENEFIT | MEDIUM_BENEFIT


def classify(zone_class):
    if zone_class in HIGH_BENEFIT:
        return "high"
    elif zone_class in MEDIUM_BENEFIT:
        return "medium"
    return "other"


def style_feature(feature):
    tier = feature["properties"]["benefit_tier"]
    if tier == "high":
        return {"fillColor": "#e63946", "color": "#e63946", "weight": 0.5, "fillOpacity": 0.6}
    elif tier == "medium":
        return {"fillColor": "#f4a261", "color": "#f4a261", "weight": 0.5, "fillOpacity": 0.5}
    return {"fillColor": "#d3d3d3", "color": "#aaaaaa", "weight": 0.2, "fillOpacity": 0.15}


def main():
    print("Loading from PostGIS...")
    engine = create_engine(DB_URL)
    gdf = gpd.read_postgis("SELECT zone_class, geometry FROM zoning_districts", engine, geom_col="geometry")
    print(f"  {len(gdf)} districts loaded (SRID: {gdf.crs.to_epsg()})")

    # Reproject from EPSG:3435 (IL State Plane) to EPSG:4326 (lat/lon) for web map
    gdf = gdf.to_crs(epsg=4326)

    gdf["benefit_tier"] = gdf["zone_class"].apply(classify)

    # Sort so background draws first, highlighted zones on top
    tier_order = {"other": 0, "medium": 1, "high": 2}
    gdf["_sort"] = gdf["benefit_tier"].map(tier_order)
    gdf = gdf.sort_values("_sort").drop(columns=["_sort"])

    print("Building map...")
    m = folium.Map(location=[41.8781, -87.6298], zoom_start=11, tiles="cartodbpositron")

    # Background zones (light gray, low opacity)
    bg = gdf[gdf["benefit_tier"] == "other"]
    if len(bg) > 0:
        folium.GeoJson(
            bg,
            style_function=style_feature,
            tooltip=folium.GeoJsonTooltip(fields=["zone_class"], aliases=["Zone:"]),
        ).add_to(m)

    # Medium benefit zones
    med = gdf[gdf["benefit_tier"] == "medium"]
    if len(med) > 0:
        folium.GeoJson(
            med,
            name="Medium Benefit (B/C -3, -5)",
            style_function=style_feature,
            tooltip=folium.GeoJsonTooltip(fields=["zone_class", "benefit_tier"], aliases=["Zone:", "Benefit:"]),
        ).add_to(m)

    # High benefit zones
    high = gdf[gdf["benefit_tier"] == "high"]
    if len(high) > 0:
        folium.GeoJson(
            high,
            name="High Benefit (B1-3, C1-2, RM-5)",
            style_function=style_feature,
            tooltip=folium.GeoJsonTooltip(fields=["zone_class", "benefit_tier"], aliases=["Zone:", "Benefit:"]),
        ).add_to(m)

    # Ward boundaries overlay
    print("Loading ward boundaries...")
    wards = gpd.read_file(WARDS_GEOJSON)[["ward", "geometry"]]
    folium.GeoJson(
        wards,
        name="Ward Boundaries",
        style_function=lambda f: {
            "fillOpacity": 0,
            "color": "#264653",
            "weight": 1.5,
            "dashArray": "5 3",
        },
        tooltip=folium.GeoJsonTooltip(fields=["ward"], aliases=["Ward:"]),
    ).add_to(m)

    folium.LayerControl().add_to(m)

    # Legend
    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background: white; padding: 12px 16px; border-radius: 8px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-family: sans-serif; font-size: 13px;">
        <b>Single Stair Benefit</b><br>
        <span style="color: #e63946;">&#9632;</span> High — B1-3, C1-2, RM-5<br>
        <span style="color: #f4a261;">&#9632;</span> Medium — B/C zones with -3, -5<br>
        <span style="color: #d3d3d3;">&#9632;</span> Other zoning<br>
        <span style="color: #264653;">- -</span> Ward boundaries
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    out = "single_stair_map.html"
    m.save(out)

    benefit_count = len(gdf[gdf["benefit_tier"] != "other"])
    total = len(gdf)
    print(f"  {benefit_count} of {total} districts highlighted as single-stair beneficiaries")
    print(f"  Map saved to {out}")


if __name__ == "__main__":
    main()
