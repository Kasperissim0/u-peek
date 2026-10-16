"""
Room & Campus Catalog Service.
Maintains building and room directories in SQLite for ALL faculties of the University of Vienna,
with extensive seed data (including PC rooms) and automated sync against university directories.
"""
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
try:
    import httpx
except ImportError:
    httpx = None
import urllib.request
from app.db import get_connection, get_meta, set_meta

logger = logging.getLogger(__name__)

# Complete list of University of Vienna faculties & main building campuses
DEFAULT_CAMPUSES = [
    {
        "id": "w29",
        "name": "Währinger Straße 29 (Informatik / Physik / Publizistik)",
        "address": "Währinger Straße 29, 1090 Wien",
        "query_prefix": "Währinger Straße 29",
        "display_order": 1,
    },
    {
        "id": "omp",
        "name": "Oskar-Morgenstern-Platz 1 (Mathematik / Wirtschaft)",
        "address": "Oskar-Morgenstern-Platz 1, 1090 Wien",
        "query_prefix": "Oskar-Morgenstern-Platz 1",
        "display_order": 2,
    },
    {
        "id": "juridicum",
        "name": "Juridicum (Schottenbastei 10-16 - Rechtswissenschaften)",
        "address": "Schottenbastei 10-16, 1010 Wien",
        "query_prefix": "Schottenbastei 10-16",
        "display_order": 3,
    },
    {
        "id": "hauptgebaeude",
        "name": "Hauptgebäude (Universitätsring 1 - Geisteswissenschaften / Rektorat)",
        "address": "Universitätsring 1, 1010 Wien",
        "query_prefix": "Hauptgebäude Universitätsring 1",
        "display_order": 4,
    },
    {
        "id": "nig",
        "name": "NIG Neues Institutsgebäude (Universitätsstraße 7 - Sozialwiss. / Philosophie)",
        "address": "Universitätsstraße 7, 1010 Wien",
        "query_prefix": "Universitätsstraße 7",
        "display_order": 5,
    },
    {
        "id": "campus",
        "name": "Campus Altes AKH (Spitalgasse 2 - Kulturwissenschaften / Sprachen)",
        "address": "Spitalgasse 2, 1090 Wien",
        "query_prefix": "Spitalgasse 2 Hof",
        "display_order": 6,
    },
    {
        "id": "ubb",
        "name": "UBB Biologiezentrum (Djerassiplatz 1 - Biologie / Lebenswissenschaften)",
        "address": "Djerassiplatz 1, 1030 Wien",
        "query_prefix": "Djerassiplatz 1",
        "display_order": 7,
    },
    {
        "id": "uza2",
        "name": "UZA II (Josef-Holaubek-Platz 2 - Pharmazie / Geowissenschaften)",
        "address": "Josef-Holaubek-Platz 2, 1090 Wien",
        "query_prefix": "Josef-Holaubek-Platz 2",
        "display_order": 8,
    },
    {
        "id": "chemie",
        "name": "Fakultät für Chemie (Währinger Straße 38-42)",
        "address": "Währinger Straße 38-42, 1090 Wien",
        "query_prefix": "Währinger Straße 38",
        "display_order": 9,
    },
    {
        "id": "physik_boltzmann",
        "name": "Fakultät für Physik (Boltzmanngasse 5 / Strudlhofgasse 4)",
        "address": "Boltzmanngasse 5, 1090 Wien",
        "query_prefix": "Boltzmanngasse 5",
        "display_order": 10,
    },
    {
        "id": "psychologie",
        "name": "Fakultät für Psychologie (Kolingasse 14-16 / Liebiggasse 5)",
        "address": "Kolingasse 14-16, 1090 Wien",
        "query_prefix": "Kolingasse 14-16",
        "display_order": 11,
    },
    {
        "id": "sport",
        "name": "Sportwissenschaft (Auf der Schmelz 6 / Sensengasse)",
        "address": "Auf der Schmelz 6, 1150 Wien",
        "query_prefix": "Auf der Schmelz 6",
        "display_order": 12,
    },
    {
        "id": "theologie",
        "name": "Theologie (Schenkenstraße 8-10)",
        "address": "Schenkenstraße 8-10, 1010 Wien",
        "query_prefix": "Schenkenstraße 8-10",
        "display_order": 13,
    },
]

# Curated room seeds per campus
SEEDED_ROOMS_MAP = {
    # 1. Währinger Straße 29 (Informatik / Physik / Publizistik)
    "w29": [
        # Hörsäle
        {"id": "hs1", "label": "HS 1", "category": "Hörsaal", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Hörsaal", "query_term": "Hörsaal 2", "display_order": 2},
        {"id": "hs3", "label": "HS 3", "category": "Hörsaal", "query_term": "Hörsaal 3", "display_order": 3},
        # Seminarräume
        {"id": "sr1", "label": "SR 1", "category": "Seminarraum", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminarraum", "query_term": "Seminarraum 2", "display_order": 12},
        {"id": "sr3", "label": "SR 3", "category": "Seminarraum", "query_term": "Seminarraum 3", "display_order": 13},
        {"id": "sr4", "label": "SR 4", "category": "Seminarraum", "query_term": "Seminarraum 4", "display_order": 14},
        {"id": "sr5", "label": "SR 5", "category": "Seminarraum", "query_term": "Seminarraum 5", "display_order": 15},
        {"id": "sr6", "label": "SR 6", "category": "Seminarraum", "query_term": "Seminarraum 6", "display_order": 16},
        {"id": "sr7", "label": "SR 7", "category": "Seminarraum", "query_term": "Seminarraum 7", "display_order": 17},
        {"id": "sr8", "label": "SR 8", "category": "Seminarraum", "query_term": "Seminarraum 8", "display_order": 18},
        {"id": "sr9", "label": "SR 9", "category": "Seminarraum", "query_term": "Seminarraum 9", "display_order": 19},
        {"id": "sr10", "label": "SR 10", "category": "Seminarraum", "query_term": "Seminarraum 10", "display_order": 20},
        {"id": "sr11", "label": "SR 11", "category": "Seminarraum", "query_term": "Seminarraum 11", "display_order": 21},
        {"id": "sr12", "label": "SR 12", "category": "Seminarraum", "query_term": "Seminarraum 12", "display_order": 22},
        # PC-Unterrichtsräume & Labs
        {"id": "pc1", "label": "PC 1", "category": "PC-Raum", "query_term": "PC-Unterrichtsraum 1", "display_order": 31},
        {"id": "pc2", "label": "PC 2", "category": "PC-Raum", "query_term": "PC-Unterrichtsraum 2", "display_order": 32},
        {"id": "pc3", "label": "PC 3", "category": "PC-Raum", "query_term": "PC-Unterrichtsraum 3", "display_order": 33},
        {"id": "pc4", "label": "PC 4", "category": "PC-Raum", "query_term": "PC-Unterrichtsraum 4", "display_order": 34},
        {"id": "pc5", "label": "PC 5", "category": "PC-Raum", "query_term": "PC-Unterrichtsraum 5", "display_order": 35},
        {"id": "pr1", "label": "Praktikumsraum 1", "category": "Labor", "query_term": "Praktikumsraum 1", "display_order": 41},
        {"id": "pr2", "label": "Praktikumsraum 2", "category": "Labor", "query_term": "Praktikumsraum 2", "display_order": 42},
    ],
    # 2. Juridicum (Rechtswissenschaften)
    "juridicum": [
        {"id": "u10", "label": "HS U10", "category": "Hörsaal", "query_term": "Hörsaal U10", "display_order": 1},
        {"id": "u11", "label": "HS U11", "category": "Hörsaal", "query_term": "Hörsaal U11", "display_order": 2},
        {"id": "u12", "label": "HS U12", "category": "Hörsaal", "query_term": "Hörsaal U12", "display_order": 3},
        {"id": "u13", "label": "HS U13", "category": "Hörsaal", "query_term": "Hörsaal U13", "display_order": 4},
        {"id": "u14", "label": "HS U14", "category": "Hörsaal", "query_term": "Hörsaal U14", "display_order": 5},
        {"id": "u15", "label": "HS U15", "category": "Hörsaal", "query_term": "Hörsaal U15", "display_order": 6},
        {"id": "u18", "label": "HS U18", "category": "Hörsaal", "query_term": "Hörsaal U18", "display_order": 7},
        {"id": "u21", "label": "HS U21", "category": "Hörsaal", "query_term": "Hörsaal U21", "display_order": 8},
        {"id": "u22", "label": "HS U22", "category": "Hörsaal", "query_term": "Hörsaal U22", "display_order": 9},
        {"id": "sem10", "label": "SEM 10", "category": "Seminarraum", "query_term": "Seminarraum 10", "display_order": 21},
        {"id": "sem20", "label": "SEM 20", "category": "Seminarraum", "query_term": "Seminarraum 20", "display_order": 22},
        {"id": "sem31", "label": "SEM 31", "category": "Seminarraum", "query_term": "Seminarraum 31", "display_order": 23},
        {"id": "sem32", "label": "SEM 32", "category": "Seminarraum", "query_term": "Seminarraum 32", "display_order": 24},
        {"id": "sem41", "label": "SEM 41", "category": "Seminarraum", "query_term": "Seminarraum 41", "display_order": 25},
        {"id": "sem42", "label": "SEM 42", "category": "Seminarraum", "query_term": "Seminarraum 42", "display_order": 26},
        {"id": "sem51", "label": "SEM 51", "category": "Seminarraum", "query_term": "Seminarraum 51", "display_order": 27},
        {"id": "sem52", "label": "SEM 52", "category": "Seminarraum", "query_term": "Seminarraum 52", "display_order": 28},
    ],
    # 3. NIG (Neues Institutsgebäude)
    "nig": [
        {"id": "hsi", "label": "HS I", "category": "Hörsaal", "query_term": "Hörsaal I", "display_order": 1},
        {"id": "hsii", "label": "HS II", "category": "Hörsaal", "query_term": "Hörsaal II", "display_order": 2},
        {"id": "hsiii", "label": "HS III", "category": "Hörsaal", "query_term": "Hörsaal III", "display_order": 3},
        {"id": "hs3b", "label": "HS 3B", "category": "Hörsaal", "query_term": "Hörsaal 3B", "display_order": 4},
        {"id": "hs3c", "label": "HS 3C", "category": "Hörsaal", "query_term": "Hörsaal 3C", "display_order": 5},
        {"id": "hs4a", "label": "HS 4A", "category": "Hörsaal", "query_term": "Hörsaal 4A", "display_order": 6},
        {"id": "hs4b", "label": "HS 4B", "category": "Hörsaal", "query_term": "Hörsaal 4B", "display_order": 7},
        {"id": "sr1", "label": "SR 1", "category": "Seminarraum", "query_term": "Seminarraum 1", "display_order": 21},
        {"id": "sr2", "label": "SR 2", "category": "Seminarraum", "query_term": "Seminarraum 2", "display_order": 22},
        {"id": "sr3", "label": "SR 3", "category": "Seminarraum", "query_term": "Seminarraum 3", "display_order": 23},
        {"id": "sr4", "label": "SR 4", "category": "Seminarraum", "query_term": "Seminarraum 4", "display_order": 24},
        {"id": "sr5", "label": "SR 5", "category": "Seminarraum", "query_term": "Seminarraum 5", "display_order": 25},
        {"id": "sr6", "label": "SR 6", "category": "Seminarraum", "query_term": "Seminarraum 6", "display_order": 26},
    ],
    # 4. Oskar-Morgenstern-Platz 1 (Mathematik & Wirtschaft)
    "omp": [
        *[{"id": f"hs{i}", "label": f"HS {i}", "category": "Hörsaal", "query_term": f"Hörsaal {i}", "display_order": i} for i in range(1, 18)],
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminarraum", "query_term": f"Seminarraum {i}", "display_order": 20 + i} for i in range(1, 17)],
        *[{"id": f"pc{i}", "label": f"PC {i}", "category": "PC-Raum", "query_term": f"PC-Raum {i}", "display_order": 50 + i} for i in range(1, 8)],
    ],
    # 5. Hauptgebäude (Universitätsring 1)
    "hauptgebaeude": [
        {"id": "audimax", "label": "Audimax", "category": "Hörsaal", "query_term": "Audimax", "display_order": 1},
        {"id": "gr_festsaal", "label": "Großer Festsaal", "category": "Hörsaal", "query_term": "Großer Festsaal", "display_order": 2},
        {"id": "kl_festsaal", "label": "Kleiner Festsaal", "category": "Hörsaal", "query_term": "Kleiner Festsaal", "display_order": 3},
        {"id": "hs1", "label": "HS 1", "category": "Hörsaal", "query_term": "Hörsaal 1", "display_order": 10},
        {"id": "hs2", "label": "HS 2", "category": "Hörsaal", "query_term": "Hörsaal 2", "display_order": 11},
        {"id": "hs3", "label": "HS 3", "category": "Hörsaal", "query_term": "Hörsaal 3", "display_order": 12},
        {"id": "hs5", "label": "HS 5", "category": "Hörsaal", "query_term": "Hörsaal 5", "display_order": 13},
        {"id": "hs7", "label": "HS 7", "category": "Hörsaal", "query_term": "Hörsaal 7", "display_order": 14},
        {"id": "hs16", "label": "HS 16", "category": "Hörsaal", "query_term": "Hörsaal 16", "display_order": 15},
        {"id": "hs21", "label": "HS 21", "category": "Hörsaal", "query_term": "Hörsaal 21", "display_order": 16},
        {"id": "hs27", "label": "HS 27", "category": "Hörsaal", "query_term": "Hörsaal 27", "display_order": 17},
        {"id": "hs30", "label": "HS 30", "category": "Hörsaal", "query_term": "Hörsaal 30", "display_order": 18},
        {"id": "hs31", "label": "HS 31", "category": "Hörsaal", "query_term": "Hörsaal 31", "display_order": 19},
        {"id": "hs32", "label": "HS 32", "category": "Hörsaal", "query_term": "Hörsaal 32", "display_order": 20},
        {"id": "hs33", "label": "HS 33", "category": "Hörsaal", "query_term": "Hörsaal 33", "display_order": 21},
        {"id": "hs34", "label": "HS 34", "category": "Hörsaal", "query_term": "Hörsaal 34", "display_order": 22},
        {"id": "hs42", "label": "HS 42", "category": "Hörsaal", "query_term": "Hörsaal 42", "display_order": 23},
        {"id": "hs50", "label": "HS 50", "category": "Hörsaal", "query_term": "Hörsaal 50", "display_order": 24},
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminarraum", "query_term": f"Seminarraum {i}", "display_order": 40 + i} for i in range(1, 9)],
    ],
    # 6. Campus Altes AKH (Spitalgasse 2)
    "campus": [
        {"id": "hsa", "label": "HS A", "category": "Hörsaal", "query_term": "Hörsaal A", "display_order": 1},
        {"id": "hsb", "label": "HS B", "category": "Hörsaal", "query_term": "Hörsaal B", "display_order": 2},
        {"id": "hsc1", "label": "HS C1", "category": "Hörsaal", "query_term": "Hörsaal C1", "display_order": 3},
        {"id": "hsc2", "label": "HS C2", "category": "Hörsaal", "query_term": "Hörsaal C2", "display_order": 4},
        {"id": "hsd", "label": "HS D", "category": "Hörsaal", "query_term": "Hörsaal D", "display_order": 5},
        {"id": "sr1", "label": "SR 1", "category": "Seminarraum", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminarraum", "query_term": "Seminarraum 2", "display_order": 12},
        {"id": "kapelle", "label": "Alte Kapelle", "category": "Hörsaal", "query_term": "Alte Kapelle", "display_order": 21},
        {"id": "aula", "label": "Aula", "category": "Hörsaal", "query_term": "Aula", "display_order": 22},
    ],
    # 7. UBB Biologiezentrum (Djerassiplatz 1)
    "ubb": [
        {"id": "hs1", "label": "HS 1", "category": "Hörsaal", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Hörsaal", "query_term": "Hörsaal 2", "display_order": 2},
        {"id": "hs3", "label": "HS 3", "category": "Hörsaal", "query_term": "Hörsaal 3", "display_order": 3},
        {"id": "hs4", "label": "HS 4", "category": "Hörsaal", "query_term": "Hörsaal 4", "display_order": 4},
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminarraum", "query_term": f"Seminarraum {i}", "display_order": 10 + i} for i in range(1, 15)],
    ],
    # 8. UZA II (Josef-Holaubek-Platz 2 / Althanstraße 14)
    "uza2": [
        *[{"id": f"hs{i}", "label": f"HS {i}", "category": "Hörsaal", "query_term": f"Hörsaal {i}", "display_order": i} for i in range(1, 9)],
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminarraum", "query_term": f"Seminarraum {i}", "display_order": 20 + i} for i in range(1, 11)],
        {"id": "pc1", "label": "PC 1", "category": "PC-Raum", "query_term": "PC-Raum 1", "display_order": 41},
        {"id": "pc2", "label": "PC 2", "category": "PC-Raum", "query_term": "PC-Raum 2", "display_order": 42},
    ],
    # 9. Fakultät für Chemie (Währinger Straße 38-42)
    "chemie": [
        {"id": "auer", "label": "Auer-v-Welsbach HS", "category": "Hörsaal", "query_term": "Carl-Auer-von-Welsbach-Hörsaal", "display_order": 1},
        {"id": "spaeth", "label": "Ernst-Späth HS", "category": "Hörsaal", "query_term": "Ernst-Späth-Hörsaal", "display_order": 2},
        {"id": "kl_hs", "label": "Kleiner Hörsaal", "category": "Hörsaal", "query_term": "Kleiner Hörsaal", "display_order": 3},
        {"id": "gr_hs", "label": "Großer Hörsaal", "category": "Hörsaal", "query_term": "Großer Hörsaal", "display_order": 4},
        {"id": "sr1", "label": "SR 1", "category": "Seminarraum", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminarraum", "query_term": "Seminarraum 2", "display_order": 12},
    ],
    # 10. Fakultät für Physik (Boltzmanngasse 5 / Strudlhofgasse 4)
    "physik_boltzmann": [
        {"id": "doppler", "label": "Doppler HS", "category": "Hörsaal", "query_term": "Christian Doppler", "display_order": 1},
        {"id": "meitner", "label": "Lise Meitner HS", "category": "Hörsaal", "query_term": "Lise Meitner", "display_order": 2},
        {"id": "hess", "label": "Hess HS", "category": "Hörsaal", "query_term": "Victor Franz Hess", "display_order": 3},
        {"id": "schroedinger", "label": "Schrödinger HS", "category": "Hörsaal", "query_term": "Erwin Schrödinger", "display_order": 4},
        {"id": "sr1", "label": "SR 1", "category": "Seminarraum", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminarraum", "query_term": "Seminarraum 2", "display_order": 12},
    ],
    # 11. Fakultät für Psychologie (Kolingasse 14-16 / Liebiggasse 5)
    "psychologie": [
        {"id": "hs1", "label": "HS 1", "category": "Hörsaal", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Hörsaal", "query_term": "Hörsaal 2", "display_order": 2},
        {"id": "hs3", "label": "HS 3", "category": "Hörsaal", "query_term": "Hörsaal 3", "display_order": 3},
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminarraum", "query_term": f"Seminarraum {i}", "display_order": 10 + i} for i in range(1, 9)],
    ],
    # 12. Sportwissenschaft (Auf der Schmelz 6)
    "sport": [
        {"id": "hs1", "label": "HS 1", "category": "Hörsaal", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Hörsaal", "query_term": "Hörsaal 2", "display_order": 2},
        {"id": "sr1", "label": "SR 1", "category": "Seminarraum", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminarraum", "query_term": "Seminarraum 2", "display_order": 12},
    ],
    # 13. Theologie (Schenkenstraße 8-10)
    "theologie": [
        {"id": "hs1", "label": "HS 1", "category": "Hörsaal", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Hörsaal", "query_term": "Hörsaal 2", "display_order": 2},
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminarraum", "query_term": f"Seminarraum {i}", "display_order": 10 + i} for i in range(1, 6)],
    ],
}


def seed_database_if_empty(force: bool = False):
    """
    Populates or updates all campuses and rooms across all faculties.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # 1. Insert/Update Campuses
        for c in DEFAULT_CAMPUSES:
            cursor.execute("""
                INSERT INTO campuses (id, name, address, query_prefix, display_order)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    address = excluded.address,
                    query_prefix = excluded.query_prefix,
                    display_order = excluded.display_order
            """, (c["id"], c["name"], c["address"], c["query_prefix"], c["display_order"]))
        
        # 2. Insert/Update Rooms for all Campuses
        for campus_id, rooms in SEEDED_ROOMS_MAP.items():
            for r in rooms:
                cursor.execute("""
                    INSERT INTO rooms (id, campus_id, label, category, query_term, display_order, last_synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campus_id, id) DO UPDATE SET
                        label = excluded.label,
                        category = excluded.category,
                        query_term = excluded.query_term,
                        display_order = excluded.display_order,
                        last_synced = excluded.last_synced
                """, (r["id"], campus_id, r["label"], r["category"], r["query_term"], r["display_order"], now_iso))
                
        conn.commit()


def get_all_campuses() -> List[Dict[str, Any]]:
    """Returns all university campuses sorted by display order."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campuses ORDER BY display_order ASC, name ASC")
        return [dict(row) for row in cursor.fetchall()]


def get_rooms_for_campus(campus_id: str) -> List[Dict[str, Any]]:
    """Returns all rooms for a given campus sorted by display order and label."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM rooms
            WHERE campus_id = ?
            ORDER BY display_order ASC, label ASC
        """, (campus_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_room_details(campus_id: str, room_id: str) -> Optional[Dict[str, Any]]:
    """Returns details for a specific room."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, c.name as campus_name, c.query_prefix
            FROM rooms r
            JOIN campuses c ON r.campus_id = c.id
            WHERE r.campus_id = ? AND r.id = ?
        """, (campus_id, room_id))
        row = cursor.fetchone()
        return dict(row) if row else None


async def sync_rooms_from_directory() -> Dict[str, Any]:
    """
    Crawls https://event.univie.ac.at/services/raumuebersicht to discover
    all university buildings and rooms, inserting new rooms and updating timestamps.
    """
    url = "https://event.univie.ac.at/services/raumuebersicht"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; UnivieRoomLookup/1.0)"}
    
    discovered_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    html = ""
    
    try:
        if httpx is not None:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    html = resp.text
        else:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='ignore')
                
        if not html:
            return {"status": "skipped", "message": "Could not fetch remote directory"}
            
        matches = re.findall(r'href="/([a-zA-Z0-9_-]+)/([a-zA-Z0-9_-]+)"', html)
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM campuses")
            valid_campuses = {row["id"] for row in cursor.fetchall()}
            
            for campus_slug, room_slug in matches:
                if campus_slug not in valid_campuses:
                    continue
                
                category = "Raum"
                label = room_slug.replace("-", " ").title()
                query_term = label
                display_order = 100
                
                if "hoersaal" in room_slug:
                    category = "Hörsaal"
                    num = re.sub(r'[^0-9a-zA-Z]', '', room_slug.replace("hoersaal", ""))
                    label = f"HS {num}".strip()
                    query_term = f"Hörsaal {num}".strip()
                    display_order = 10 + (int(num) if num.isdigit() else 0)
                elif "seminarraum" in room_slug:
                    category = "Seminarraum"
                    num = re.sub(r'[^0-9a-zA-Z]', '', room_slug.replace("seminarraum", ""))
                    label = f"SR {num}".strip()
                    query_term = f"Seminarraum {num}".strip()
                    display_order = 50 + (int(num) if num.isdigit() else 0)
                elif "pc-raum" in room_slug or "pc-unterrichtsraum" in room_slug:
                    category = "PC-Raum"
                    num = re.sub(r'[^0-9a-zA-Z]', '', room_slug.replace("pc-unterrichtsraum", "").replace("pc-raum", ""))
                    label = f"PC {num}".strip()
                    query_term = f"PC-Unterrichtsraum {num}".strip()
                    display_order = 80 + (int(num) if num.isdigit() else 0)
                elif "audimax" in room_slug:
                    category = "Hörsaal"
                    label = "Audimax"
                    query_term = "Audimax"
                    display_order = 1
                
                cursor.execute("""
                    INSERT INTO rooms (id, campus_id, label, category, query_term, display_order, last_synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campus_id, id) DO UPDATE SET
                        label = excluded.label,
                        category = excluded.category,
                        query_term = excluded.query_term,
                        last_synced = excluded.last_synced
                """, (room_slug, campus_slug, label, category, query_term, display_order, now_iso))
                discovered_count += 1
            
            conn.commit()
            set_meta("last_room_sync", now_iso)
            
        return {"status": "ok", "rooms_synced": discovered_count, "synced_at": now_iso}
    except Exception as e:
        logger.error(f"Error syncing room directory: {e}")
        return {"status": "error", "message": str(e)}


async def check_auto_sync_needed():
    """Checks if room sync has never run or is older than 30 days, running it if needed."""
    last_sync = get_meta("last_room_sync")
    if not last_sync:
        await sync_rooms_from_directory()
        return
    
    try:
        last_dt = datetime.fromisoformat(last_sync)
        if (datetime.now(timezone.utc) - last_dt).days >= 30:
            logger.info("Room directory sync is > 30 days old. Refreshing...")
            await sync_rooms_from_directory()
    except Exception as e:
        logger.warning(f"Could not parse last_room_sync timestamp: {e}")
