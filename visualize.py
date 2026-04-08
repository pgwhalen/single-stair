"""Visualize Chicago zoning districts that benefit from single-stair ordinance."""

import json

import geopandas as gpd
import folium
from sqlalchemy import create_engine

DB_URL = "postgresql://pgwhalen@localhost:5432/urbanism"
WARDS_GEOJSON = "Boundaries_-_Wards_(2023-)_20260407.geojson"

# Zones that benefit from single-stair ordinance:
# - Business (B) and Commercial (C) zones with -3 or -5 density suffix
# - RM-5 (residential multi-unit)
# - C1-2 (neighborhood commercial, lower density but explicitly included)
SINGLE_STAIR_BENEFIT = {
    "B1-3", "B1-5", "B2-3", "B2-5", "B3-3", "B3-5",
    "C1-2", "C1-3", "C1-5", "C2-3", "C2-5", "C3-3", "C3-5",
    "RM-5",
}


def classify(zone_class):
    if zone_class in SINGLE_STAIR_BENEFIT:
        return "benefit"
    return "other"


def main():
    print("Loading from PostGIS...")
    engine = create_engine(DB_URL)
    gdf = gpd.read_postgis("SELECT zone_class, geometry FROM zoning_districts", engine, geom_col="geometry")
    print(f"  {len(gdf)} districts loaded (SRID: {gdf.crs.to_epsg()})")

    # Reproject from EPSG:3435 (IL State Plane) to EPSG:4326 (lat/lon) for web map
    gdf = gdf.to_crs(epsg=4326)
    gdf["benefit_tier"] = gdf["zone_class"].apply(classify)

    print("Loading ward boundaries...")
    wards = gpd.read_file(WARDS_GEOJSON)[["ward", "geometry"]]

    # Spatial join: assign each zoning district to a ward
    print("Spatial join: zoning districts -> wards...")
    gdf_with_ward = gpd.sjoin(gdf, wards, how="left", predicate="intersects")
    # Some districts may span ward boundaries; keep the first match
    gdf_with_ward = gdf_with_ward[~gdf_with_ward.index.duplicated(keep="first")]
    gdf_with_ward["ward"] = gdf_with_ward["ward"].fillna("Unknown").astype(str)
    # Convert ward to int for sorting where possible
    gdf_with_ward["ward_num"] = gdf_with_ward["ward"].apply(
        lambda w: int(w) if w.isdigit() else 999
    )

    print("Building map...")
    m = folium.Map(location=[41.8781, -87.6298], zoom_start=11, tiles="cartodbpositron")

    # Serialize zoning data as a single GeoJSON blob with ward + tier properties
    zoning_geojson = json.loads(gdf_with_ward[["zone_class", "benefit_tier", "ward", "geometry"]].to_json())
    wards_geojson = json.loads(wards.to_json())

    # Inject all data and interactivity via custom HTML/JS
    custom_html = f"""
    <style>
        #ward-filter {{
            position: fixed;
            top: 12px;
            right: 12px;
            z-index: 1000;
            background: white;
            padding: 10px 14px;
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            font-family: sans-serif;
            font-size: 13px;
        }}
        #ward-filter select {{
            margin-top: 4px;
            padding: 4px 8px;
            font-size: 13px;
            border-radius: 4px;
            border: 1px solid #ccc;
            width: 100%;
        }}
        #ward-info {{
            margin-top: 8px;
            font-size: 12px;
            color: #555;
        }}
        #legend {{
            position: fixed;
            bottom: 30px;
            left: 30px;
            z-index: 1000;
            background: white;
            padding: 12px 16px;
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            font-family: sans-serif;
            font-size: 13px;
        }}
    </style>

    <div id="ward-filter">
        <b>Filter by Ward</b><br>
        <select id="ward-select">
            <option value="all">All Wards</option>
        </select>
        <div id="ward-info"></div>
    </div>

    <div id="legend">
        <b>Single Stair Benefit</b><br>
        <span style="color: #e63946;">&#9632;</span> Eligible — B/C with -3 or -5, C1-2, RM-5<br>
        <span style="color: #d3d3d3;">&#9632;</span> Other zoning<br>
        <span style="color: #264653;">- -</span> Ward boundaries
    </div>

    <script>
    (function() {{
        // Wait for map to be ready
        var checkMap = setInterval(function() {{
            var mapEl = document.querySelector('.folium-map');
            if (!mapEl || !mapEl._leaflet_id) return;
            clearInterval(checkMap);

            var map = mapEl._leaflet_map || null;
            // Find the Leaflet map instance
            for (var key in window) {{
                if (window[key] instanceof L.Map) {{
                    map = window[key];
                    break;
                }}
            }}
            if (!map) return;

            var zoningData = {json.dumps(zoning_geojson)};
            var wardsData = {json.dumps(wards_geojson)};

            var tierStyles = {{
                'benefit': {{fillColor: '#e63946', color: '#e63946', weight: 0.5, fillOpacity: 0.6}},
                'other':   {{fillColor: '#d3d3d3', color: '#aaaaaa', weight: 0.2, fillOpacity: 0.15}}
            }};

            var wardStyle = {{fillOpacity: 0, color: '#264653', weight: 1.5, dashArray: '5 3'}};
            var wardHighlightStyle = {{fillOpacity: 0.05, fillColor: '#264653', color: '#264653', weight: 2.5, dashArray: null}};

            var zoningLayer = null;
            var wardsLayer = null;

            function styleZoning(feature) {{
                return tierStyles[feature.properties.benefit_tier] || tierStyles['other'];
            }}

            function renderLayers(selectedWard) {{
                if (zoningLayer) map.removeLayer(zoningLayer);
                if (wardsLayer) map.removeLayer(wardsLayer);

                // Filter zoning features
                var filteredZoning = {{type: 'FeatureCollection', features: []}};
                if (selectedWard === 'all') {{
                    filteredZoning.features = zoningData.features;
                }} else {{
                    filteredZoning.features = zoningData.features.filter(function(f) {{
                        return f.properties.ward === selectedWard;
                    }});
                }}

                // Sort: other first, then benefit on top
                filteredZoning.features.sort(function(a, b) {{
                    var order = {{'other': 0, 'benefit': 1}};
                    return (order[a.properties.benefit_tier] || 0) -
                           (order[b.properties.benefit_tier] || 0);
                }});

                zoningLayer = L.geoJson(filteredZoning, {{
                    style: styleZoning,
                    onEachFeature: function(feature, layer) {{
                        var p = feature.properties;
                        var tip = '<b>Zone:</b> ' + p.zone_class +
                                  '<br><b>Benefit:</b> ' + p.benefit_tier +
                                  '<br><b>Ward:</b> ' + p.ward;
                        layer.bindTooltip(tip);
                    }}
                }}).addTo(map);

                wardsLayer = L.geoJson(wardsData, {{
                    style: function(feature) {{
                        if (selectedWard !== 'all' && feature.properties.ward === selectedWard) {{
                            return wardHighlightStyle;
                        }}
                        return wardStyle;
                    }},
                    onEachFeature: function(feature, layer) {{
                        layer.bindTooltip('<b>Ward:</b> ' + feature.properties.ward);
                        layer.on('click', function() {{
                            var w = feature.properties.ward;
                            var sel = document.getElementById('ward-select');
                            sel.value = w;
                            sel.dispatchEvent(new Event('change'));
                        }});
                    }}
                }}).addTo(map);

                // Update info
                var info = document.getElementById('ward-info');
                if (selectedWard === 'all') {{
                    var totalBenefit = zoningData.features.filter(function(f) {{
                        return f.properties.benefit_tier !== 'other';
                    }}).length;
                    info.innerHTML = totalBenefit + ' beneficiary districts city-wide';
                }} else {{
                    var total = filteredZoning.features.length;
                    var benefit = filteredZoning.features.filter(function(f) {{
                        return f.properties.benefit_tier !== 'other';
                    }}).length;
                    info.innerHTML = benefit + ' of ' + total + ' districts benefit';

                    // Zoom to ward
                    var wardFeature = wardsData.features.find(function(f) {{
                        return f.properties.ward === selectedWard;
                    }});
                    if (wardFeature) {{
                        var wardLayer = L.geoJson(wardFeature);
                        map.fitBounds(wardLayer.getBounds(), {{padding: [30, 30]}});
                    }}
                }}
            }}

            // Populate dropdown
            var select = document.getElementById('ward-select');
            var wardNumbers = wardsData.features.map(function(f) {{
                return f.properties.ward;
            }}).sort(function(a, b) {{ return parseInt(a) - parseInt(b); }});

            wardNumbers.forEach(function(w) {{
                var opt = document.createElement('option');
                opt.value = w;
                opt.textContent = 'Ward ' + w;
                select.appendChild(opt);
            }});

            select.addEventListener('change', function() {{
                renderLayers(this.value);
            }});

            // Initial render
            renderLayers('all');
        }}, 100);
    }})();
    </script>
    """

    m.get_root().html.add_child(folium.Element(custom_html))

    out = "single_stair_map.html"
    m.save(out)

    benefit_count = len(gdf_with_ward[gdf_with_ward["benefit_tier"] != "other"])
    total = len(gdf_with_ward)
    print(f"  {benefit_count} of {total} districts highlighted as single-stair beneficiaries")
    print(f"  Map saved to {out}")


if __name__ == "__main__":
    main()
