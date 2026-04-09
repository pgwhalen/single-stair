# Single Stair Zoning Visualization

Visualizes Chicago zoning districts that stand to benefit most from a "single stair" building ordinance — which allows buildings with a single staircase (common in European construction), enabling more efficient use of smaller lots for mid-rise residential and mixed-use development.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python visualize.py
open single_stair_map.html
```

No database required — reads directly from data files in `data/`.

## Data

Both files are from Chicago Open Data:

- `data/Boundaries_-_Zoning_Districts_(current)_20260407.csv` — [14,874 zoning districts](https://data.cityofchicago.org/Community-Economic-Development/Boundaries-Zoning-Districts-current-/7cve-jgbp) with WKT geometries
- `data/Boundaries_-_Wards_(2023-)_20260407.geojson` — [Ward boundaries](https://data.cityofchicago.org/Facilities-Geographic-Boundaries/Boundaries-Wards-2023-Map/cdf7-bgn3)

## Scripts

- **visualize.py** — Classifies zones by single-stair benefit tier, outputs `single_stair_map.html` (interactive Folium map). By default reads from CSV; use `--source postgres` to read from PostGIS instead.
- **load_data.py** — Parses the CSV and loads into PostGIS table `zoning_districts`.
- **setup_db.py** — Creates the PostGIS extension in the `urbanism` database (run once before `load_data.py`).

## PostgreSQL Setup (Optional)

Only needed if you want to use `--source postgres`:

```bash
# Create a .env file with your connection string
echo 'DB_URL=postgresql://user@localhost:5432/urbanism' > .env

createdb urbanism
python setup_db.py       # enables PostGIS extension
python load_data.py      # loads CSV into zoning_districts table
python visualize.py --source postgres
```

All database scripts read `DB_URL` from the environment (or `.env` file).

## Dependencies

All Python dependencies are pinned in `requirements.txt`.

```bash
pip install -r requirements.txt          # install
pip install some-new-package && pip freeze > requirements.txt  # add a package
pip freeze > requirements.txt            # update after any pip install/upgrade
```

For PostgreSQL support: psycopg2-binary, sqlalchemy, GeoAlchemy2 (already included).
System: PostgreSQL 17 (Homebrew), PostGIS extension.
