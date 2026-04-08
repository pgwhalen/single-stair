# Single Stair Zoning Visualization

Visualizes Chicago zoning districts that stand to benefit most from a "single stair" building ordinance — which allows buildings with a single staircase (common in European construction), enabling more efficient use of smaller lots for mid-rise residential and mixed-use development.

## Setup

```bash
# Activate virtual environment
source .venv/bin/activate

# Database: PostgreSQL 17 with PostGIS, database "urbanism"
# Connection: postgresql://pgwhalen@localhost:5432/urbanism
# Table: zoning_districts (14,874 rows)
```

## Scripts

- **load_data.py** — Reads `Boundaries_-_Zoning_Districts_(current)_20260407.csv` (Chicago open data), parses WKT geometries, and loads into PostGIS table `zoning_districts`.
- **visualize.py** — Queries PostGIS, classifies zones by single-stair benefit tier, outputs `single_stair_map.html` (interactive Folium map).

## Target Zone Classes

**High benefit** (red): B1-3, C1-2, RM-5
**Medium benefit** (orange): Business/commercial zones with -3 or -5 suffix — B1-5, B2-3, B2-5, B3-3, B3-5, C1-3, C1-5, C2-3, C2-5, C3-3, C3-5

Rationale: These zones allow new mixed-use or residential construction on smaller lots (often vacant lots next to existing stores). Single-stair designs unlock feasible development on parcels that would otherwise be too narrow for double-stair buildings.

## Dependencies

Python packages (in .venv): geopandas, psycopg2-binary, sqlalchemy, folium, shapely, matplotlib, GeoAlchemy2
System: PostgreSQL 17 (Homebrew), PostGIS extension
