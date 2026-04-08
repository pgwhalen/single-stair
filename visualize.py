"""Visualize Chicago zoning districts that benefit from single-stair ordinance."""

import json

import geopandas as gpd
import folium
from sqlalchemy import create_engine

DB_URL = "postgresql://pgwhalen@localhost:5432/urbanism"
WARDS_GEOJSON = "Boundaries_-_Wards_(2023-)_20260407.geojson"

# Single-stair benefit tiers, per STC feedback (Alex Montero / Steven):
#
# FULLY RESIDENTIAL (green tones):
#   res_7   — 7 dupsl:  RM-5, RM-5.5, B2-3
#   res_10  — 10 dupsl: RM-6, RM-6.5
#   res_15  — 15 dupsl: B2-5
#
# GROUND-FLOOR COMMERCIAL REQUIRED (blue tones):
#   com_7   — 7 dupsl:  B1-3, B3-3, C1-3, C2-3
#   com_15  — 15 dupsl: B1-5, B3-5, C1-5, C2-5

TIER_MAP = {
    # Fully residential
    "RM-5":   "res_7",
    "RM-5.5": "res_7",
    "B2-3":   "res_7",
    "RM-6":   "res_10",
    "RM-6.5": "res_10",
    "B2-5":   "res_15",
    # Ground-floor commercial required
    "B1-3":   "com_7",
    "B3-3":   "com_7",
    "C1-3":   "com_7",
    "C2-3":   "com_7",
    "B1-5":   "com_15",
    "B3-5":   "com_15",
    "C1-5":   "com_15",
    "C2-5":   "com_15",
}

TIER_LABELS = {
    "res_7":  "Fully residential — 7 du/lot",
    "res_10": "Fully residential — 10 du/lot",
    "res_15": "Fully residential — 15 du/lot",
    "com_7":  "Ground-floor commercial — 7 du/lot",
    "com_15": "Ground-floor commercial — 15 du/lot",
    "other":  "Other zoning",
}


def classify(zone_class):
    return TIER_MAP.get(zone_class, "other")


def main():
    print("Loading from PostGIS...")
    engine = create_engine(DB_URL)
    gdf = gpd.read_postgis(
        "SELECT zone_class, shape_area, geometry FROM zoning_districts",
        engine, geom_col="geometry",
    )
    print(f"  {len(gdf)} districts loaded (SRID: {gdf.crs.to_epsg()})")

    # Reproject from EPSG:3435 (IL State Plane) to EPSG:4326 (lat/lon) for web map
    gdf = gdf.to_crs(epsg=4326)
    gdf["benefit_tier"] = gdf["zone_class"].apply(classify)

    print("Loading ward boundaries...")
    wards = gpd.read_file(WARDS_GEOJSON)[["ward", "geometry"]]

    # Spatial join: assign each zoning district to a ward
    print("Spatial join: zoning districts -> wards...")
    gdf_with_ward = gpd.sjoin(gdf, wards, how="left", predicate="intersects")
    gdf_with_ward = gdf_with_ward[~gdf_with_ward.index.duplicated(keep="first")]
    gdf_with_ward["ward"] = gdf_with_ward["ward"].fillna("Unknown").astype(str)
    gdf_with_ward["ward_num"] = gdf_with_ward["ward"].apply(
        lambda w: int(w) if w.isdigit() else 999
    )

    # Add human-readable tier label as a property for tooltips
    gdf_with_ward["tier_label"] = gdf_with_ward["benefit_tier"].map(TIER_LABELS)

    # Clean up shape_area: remove commas, convert to float, then to acres
    gdf_with_ward["area_sqft"] = (
        gdf_with_ward["shape_area"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .astype(float)
    )
    gdf_with_ward["area_acres"] = (gdf_with_ward["area_sqft"] / 43560).round(2)

    print("Building map...")
    m = folium.Map(location=[41.8781, -87.6298], zoom_start=11, tiles="cartodbpositron")

    zoning_geojson = json.loads(
        gdf_with_ward[[
            "zone_class", "benefit_tier", "tier_label", "ward",
            "area_sqft", "area_acres", "geometry",
        ]].to_json()
    )
    wards_geojson = json.loads(wards.to_json())

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
            font-size: 12px;
            line-height: 1.7;
            max-width: 310px;
        }}
        #legend .section-label {{
            font-weight: bold;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #555;
            margin-top: 6px;
            margin-bottom: 2px;
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
        <b style="font-size:14px;">Single Stair Benefit</b>
        <div class="section-label">Can be fully residential</div>
        <span style="color: #8bc34a;">&#9632;</span> 7 du/lot — RM-5, RM-5.5, B2-3<br>
        <span style="color: #4caf50;">&#9632;</span> 10 du/lot — RM-6, RM-6.5<br>
        <span style="color: #2e7d32;">&#9632;</span> 15 du/lot — B2-5<br>
        <div class="section-label">Ground-floor commercial required</div>
        <span style="color: #64b5f6;">&#9632;</span> 7 du/lot — B1-3, B3-3, C1-3, C2-3<br>
        <span style="color: #1565c0;">&#9632;</span> 15 du/lot — B1-5, B3-5, C1-5, C2-5<br>
        <div style="margin-top:4px;">
        <span style="color: #d3d3d3;">&#9632;</span> Other zoning<br>
        <span style="color: #264653;">- -</span> Ward boundaries
        </div>
    </div>

    <script>
    (function() {{
        var checkMap = setInterval(function() {{
            var mapEl = document.querySelector('.folium-map');
            if (!mapEl || !mapEl._leaflet_id) return;
            clearInterval(checkMap);

            var map = null;
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
                'res_7':   {{fillColor: '#8bc34a', color: '#7cb342', weight: 0.5, fillOpacity: 0.65}},
                'res_10':  {{fillColor: '#4caf50', color: '#43a047', weight: 0.5, fillOpacity: 0.65}},
                'res_15':  {{fillColor: '#2e7d32', color: '#256427', weight: 0.5, fillOpacity: 0.65}},
                'com_7':   {{fillColor: '#64b5f6', color: '#5a9fd4', weight: 0.5, fillOpacity: 0.65}},
                'com_15':  {{fillColor: '#1565c0', color: '#0d47a1', weight: 0.5, fillOpacity: 0.65}},
                'other':   {{fillColor: '#d3d3d3', color: '#aaaaaa', weight: 0.2, fillOpacity: 0.15}}
            }};

            var tierOrder = {{'other': 0, 'res_7': 1, 'res_10': 2, 'res_15': 3, 'com_7': 4, 'com_15': 5}};

            // Zoning detail lookup for click popups
            var zoneInfo = {{
                'RM-5':   {{name: 'Residential Multi-Unit', far: '1.2', height: "50'", dupsl: 7, gfComm: false}},
                'RM-5.5': {{name: 'Residential Multi-Unit', far: '2.0', height: "58'", dupsl: 7, gfComm: false}},
                'RM-6':   {{name: 'Residential Multi-Unit', far: '2.2', height: "65'", dupsl: 10, gfComm: false}},
                'RM-6.5': {{name: 'Residential Multi-Unit', far: '4.4', height: "70'", dupsl: 10, gfComm: false}},
                'B2-3':   {{name: 'Neighborhood Mixed-Use', far: '1.2', height: "50'", dupsl: 7, gfComm: false}},
                'B2-5':   {{name: 'Neighborhood Mixed-Use', far: '2.0', height: "65'", dupsl: 15, gfComm: false}},
                'B1-3':   {{name: 'Neighborhood Shopping', far: '1.2', height: "50'", dupsl: 7, gfComm: true}},
                'B1-5':   {{name: 'Neighborhood Shopping', far: '2.0', height: "65'", dupsl: 15, gfComm: true}},
                'B3-3':   {{name: 'Community Shopping', far: '1.2', height: "50'", dupsl: 7, gfComm: true}},
                'B3-5':   {{name: 'Community Shopping', far: '2.0', height: "65'", dupsl: 15, gfComm: true}},
                'C1-3':   {{name: 'Neighborhood Commercial', far: '1.2', height: "50'", dupsl: 7, gfComm: true}},
                'C1-5':   {{name: 'Neighborhood Commercial', far: '2.0', height: "65'", dupsl: 15, gfComm: true}},
                'C2-3':   {{name: 'Motor Vehicle-Related Commercial', far: '1.2', height: "50'", dupsl: 7, gfComm: true}},
                'C2-5':   {{name: 'Motor Vehicle-Related Commercial', far: '2.0', height: "65'", dupsl: 15, gfComm: true}}
            }};

            var wardStyle = {{fillOpacity: 0, color: '#264653', weight: 1.5, dashArray: '5 3'}};
            var wardHighlightStyle = {{fillOpacity: 0.05, fillColor: '#264653', color: '#264653', weight: 2.5, dashArray: null}};

            var zoningLayer = null;
            var wardsLayer = null;

            function styleZoning(feature) {{
                return tierStyles[feature.properties.benefit_tier] || tierStyles['other'];
            }}

            function formatNumber(n) {{
                return n ? n.toLocaleString() : '—';
            }}

            function buildPopup(p) {{
                var zi = zoneInfo[p.zone_class];
                var html = '<div style="font-family:sans-serif;font-size:13px;line-height:1.5;min-width:220px;">';
                html += '<div style="font-size:16px;font-weight:bold;margin-bottom:4px;">' + p.zone_class + '</div>';

                if (zi) {{
                    html += '<div style="color:#555;margin-bottom:8px;">' + zi.name + '</div>';
                    html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
                    html += '<tr><td style="padding:2px 8px 2px 0;color:#777;">Density</td><td><b>' + zi.dupsl + '</b> units/standard lot</td></tr>';
                    html += '<tr><td style="padding:2px 8px 2px 0;color:#777;">Max FAR</td><td>' + zi.far + '</td></tr>';
                    html += '<tr><td style="padding:2px 8px 2px 0;color:#777;">Max Height</td><td>' + zi.height + '</td></tr>';
                    html += '<tr><td style="padding:2px 8px 2px 0;color:#777;">Ground Floor</td><td>' +
                        (zi.gfComm ? '<span style="color:#1565c0;">Commercial required</span>' : '<span style="color:#2e7d32;">Residential OK</span>') + '</td></tr>';
                    html += '</table>';
                }} else {{
                    html += '<div style="color:#999;margin-bottom:8px;">Not in single-stair benefit area</div>';
                }}

                html += '<hr style="margin:8px 0;border:none;border-top:1px solid #eee;">';
                html += '<table style="width:100%;border-collapse:collapse;font-size:12px;">';
                html += '<tr><td style="padding:2px 8px 2px 0;color:#777;">District Area</td><td>' + formatNumber(Math.round(p.area_sqft)) + ' sq ft (' + p.area_acres + ' ac)</td></tr>';
                html += '<tr><td style="padding:2px 8px 2px 0;color:#777;">Ward</td><td>' + p.ward + '</td></tr>';
                html += '</table>';
                html += '</div>';
                return html;
            }}

            function renderLayers(selectedWard) {{
                if (zoningLayer) map.removeLayer(zoningLayer);
                if (wardsLayer) map.removeLayer(wardsLayer);

                var filteredZoning = {{type: 'FeatureCollection', features: []}};
                if (selectedWard === 'all') {{
                    filteredZoning.features = zoningData.features;
                }} else {{
                    filteredZoning.features = zoningData.features.filter(function(f) {{
                        return f.properties.ward === selectedWard;
                    }});
                }}

                // Sort: other first, benefit tiers on top
                filteredZoning.features.sort(function(a, b) {{
                    return (tierOrder[a.properties.benefit_tier] || 0) -
                           (tierOrder[b.properties.benefit_tier] || 0);
                }});

                zoningLayer = L.geoJson(filteredZoning, {{
                    style: styleZoning,
                    onEachFeature: function(feature, layer) {{
                        var p = feature.properties;
                        // Lightweight hover tooltip
                        layer.bindTooltip('<b>' + p.zone_class + '</b> — ' + p.tier_label);
                        // Rich click popup
                        layer.bindPopup(buildPopup(p), {{maxWidth: 300}});
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
                        layer.bindTooltip('<b>Ward ' + feature.properties.ward + '</b>');
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

    # Breakdown by tier
    for tier, label in TIER_LABELS.items():
        if tier == "other":
            continue
        count = len(gdf_with_ward[gdf_with_ward["benefit_tier"] == tier])
        if count:
            print(f"    {tier}: {count} ({label})")

    print(f"  Map saved to {out}")


if __name__ == "__main__":
    main()
