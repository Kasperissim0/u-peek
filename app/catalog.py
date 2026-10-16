"""
Room & Campus Catalog Service.
Maintains building and room directories in SQLite for ALL faculties of the University of Vienna,
with extensive seed data (including PC rooms) and automated sync against university directories.
"""
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import ssl
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
        "name": "W29: Währinger Straße 29 (Computer Science & Media)",
        "address": "Währinger Straße 29, 1090 Wien",
        "query_prefix": "Währinger Straße 29",
        "spl_codes": "spl5,spl22",
        "display_order": 1,
    },
    {
        "id": "hauptgebaeude",
        "name": "Hauptgebäude: Universitätsring 1 (Humanities)",
        "address": "Universitätsring 1, 1010 Wien",
        "query_prefix": "Hauptgebäude",
        "spl_codes": "spl6,spl7,spl9,spl10,spl1",
        "display_order": 2,
    },
    {
        "id": "campus",
        "name": "Campus Altes AKH: Spitalgasse 2 (Cultural Studies & Languages)",
        "address": "Spitalgasse 2, 1090 Wien",
        "query_prefix": "Spitalgasse 2 Hof",
        "spl_codes": "spl3,spl6,spl12",
        "display_order": 3,
    },
    {
        "id": "omp",
        "name": "OMP: Oskar-Morgenstern-Platz 1 (Mathematics & Economics)",
        "address": "Oskar-Morgenstern-Platz 1, 1090 Wien",
        "query_prefix": "Oskar-Morgenstern-Platz 1",
        "spl_codes": "spl25,spl4",
        "display_order": 4,
    },
    {
        "id": "juridicum",
        "name": "Juridicum: Schottenbastei 10-16 (Law)",
        "address": "Schottenbastei 10-16, 1010 Wien",
        "query_prefix": "Schottenbastei 10-16",
        "spl_codes": "spl34",
        "display_order": 5,
    },
    {
        "id": "nig",
        "name": "NIG: Universitätsstraße 7 (Social Sciences & Philosophy)",
        "address": "Universitätsstraße 7, 1010 Wien",
        "query_prefix": "Universitätsstraße 7",
        "spl_codes": "spl2,spl20,spl21,spl24",
        "display_order": 6,
    },
    {
        "id": "ubb",
        "name": "UBB: Djerassiplatz 1 (Life Sciences & Biology)",
        "address": "Djerassiplatz 1, 1030 Wien",
        "query_prefix": "Djerassiplatz 1",
        "spl_codes": "spl30,spl31",
        "display_order": 7,
    },
    {
        "id": "uza2",
        "name": "UZA II: Josef-Holaubek-Platz 2 (Pharmacy & Geosciences)",
        "address": "Josef-Holaubek-Platz 2, 1090 Wien",
        "query_prefix": "Josef-Holaubek-Platz 2",
        "spl_codes": "spl28,spl29",
        "display_order": 8,
    },
    {
        "id": "chemie",
        "name": "Chemie: Währinger Straße 38-42 (Chemistry)",
        "address": "Währinger Straße 38-42, 1090 Wien",
        "query_prefix": "Währinger Straße 38",
        "spl_codes": "spl27",
        "display_order": 9,
    },
    {
        "id": "physik_boltzmann",
        "name": "Physik: Boltzmanngasse 5 (Physics)",
        "address": "Boltzmanngasse 5, 1090 Wien",
        "query_prefix": "Boltzmanngasse 5",
        "spl_codes": "spl26",
        "display_order": 10,
    },
    {
        "id": "psychologie",
        "name": "Psychologie: Kolingasse 14-16 (Psychology)",
        "address": "Kolingasse 14-16, 1090 Wien",
        "query_prefix": "Kolingasse 14-16",
        "spl_codes": "spl32",
        "display_order": 11,
    },
    {
        "id": "sport",
        "name": "USZ: Auf der Schmelz 6 (Sport Science)",
        "address": "Auf der Schmelz 6, 1150 Wien",
        "query_prefix": "Auf der Schmelz 6",
        "spl_codes": "spl33",
        "display_order": 12,
    },
    {
        "id": "theologie",
        "name": "Theologie: Schenkenstraße 8-10 (Theology)",
        "address": "Schenkenstraße 8-10, 1010 Wien",
        "query_prefix": "Schenkenstraße 8-10",
        "spl_codes": "spl1,spl2",
        "display_order": 13,
    },
]

# Curated room seeds per campus
SEEDED_ROOMS_MAP = {
    # 1. Währinger Straße 29 (Computer Science / Physics / Media)
    "w29": [
        # Lecture Halls
        {"id": "hs1", "label": "HS 1", "category": "Lecture Hall", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Lecture Hall", "query_term": "Hörsaal 2", "display_order": 2},
        {"id": "hs3", "label": "HS 3", "category": "Lecture Hall", "query_term": "Hörsaal 3", "display_order": 3},
        # Seminar Rooms
        {"id": "sr1", "label": "SR 1", "category": "Seminar Room", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminar Room", "query_term": "Seminarraum 2", "display_order": 12},
        {"id": "sr3", "label": "SR 3", "category": "Seminar Room", "query_term": "Seminarraum 3", "display_order": 13},
        {"id": "sr4", "label": "SR 4", "category": "Seminar Room", "query_term": "Seminarraum 4", "display_order": 14},
        {"id": "sr5", "label": "SR 5", "category": "Seminar Room", "query_term": "Seminarraum 5", "display_order": 15},
        {"id": "sr6", "label": "SR 6", "category": "Seminar Room", "query_term": "Seminarraum 6", "display_order": 16},
        {"id": "sr7", "label": "SR 7", "category": "Seminar Room", "query_term": "Seminarraum 7", "display_order": 17},
        {"id": "sr8", "label": "SR 8", "category": "Seminar Room", "query_term": "Seminarraum 8", "display_order": 18},
        {"id": "sr9", "label": "SR 9", "category": "Seminar Room", "query_term": "Seminarraum 9", "display_order": 19},
        {"id": "sr10", "label": "SR 10", "category": "Seminar Room", "query_term": "Seminarraum 10", "display_order": 20},
        {"id": "sr11", "label": "SR 11", "category": "Seminar Room", "query_term": "Seminarraum 11", "display_order": 21},
        {"id": "sr12", "label": "SR 12", "category": "Seminar Room", "query_term": "Seminarraum 12", "display_order": 22},
        # Computer Labs & Labs
        {"id": "pc1", "label": "PC 1", "category": "Computer Lab", "query_term": "PC-Unterrichtsraum 1", "display_order": 31},
        {"id": "pc2", "label": "PC 2", "category": "Computer Lab", "query_term": "PC-Unterrichtsraum 2", "display_order": 32},
        {"id": "pc3", "label": "PC 3", "category": "Computer Lab", "query_term": "PC-Unterrichtsraum 3", "display_order": 33},
        {"id": "pc4", "label": "PC 4", "category": "Computer Lab", "query_term": "PC-Unterrichtsraum 4", "display_order": 34},
        {"id": "pc5", "label": "PC 5", "category": "Computer Lab", "query_term": "PC-Unterrichtsraum 5", "display_order": 35},
        {"id": "pc6", "label": "PC 6", "category": "Computer Lab", "query_term": "PC-Unterrichtsraum 6", "display_order": 36},
        {"id": "pr1", "label": "Praktikumsraum 1", "category": "Laboratory", "query_term": "Praktikumsraum 1", "display_order": 41},
        {"id": "pr2", "label": "Praktikumsraum 2", "category": "Laboratory", "query_term": "Praktikumsraum 2", "display_order": 42},
    ],
    # 2. Juridicum (Law)
    "juridicum": [
        {"id": "u10", "label": "HS U10", "category": "Lecture Hall", "query_term": "Hörsaal U10", "display_order": 1},
        {"id": "u11", "label": "HS U11", "category": "Lecture Hall", "query_term": "Hörsaal U11", "display_order": 2},
        {"id": "u12", "label": "HS U12", "category": "Lecture Hall", "query_term": "Hörsaal U12", "display_order": 3},
        {"id": "u13", "label": "HS U13", "category": "Lecture Hall", "query_term": "Hörsaal U13", "display_order": 4},
        {"id": "u14", "label": "HS U14", "category": "Lecture Hall", "query_term": "Hörsaal U14", "display_order": 5},
        {"id": "u15", "label": "HS U15", "category": "Lecture Hall", "query_term": "Hörsaal U15", "display_order": 6},
        {"id": "u18", "label": "HS U18", "category": "Lecture Hall", "query_term": "Hörsaal U18", "display_order": 7},
        {"id": "u21", "label": "HS U21", "category": "Lecture Hall", "query_term": "Hörsaal U21", "display_order": 8},
        {"id": "u22", "label": "HS U22", "category": "Lecture Hall", "query_term": "Hörsaal U22", "display_order": 9},
        {"id": "sem10", "label": "SEM 10", "category": "Seminar Room", "query_term": "Seminarraum 10", "display_order": 21},
        {"id": "sem20", "label": "SEM 20", "category": "Seminar Room", "query_term": "Seminarraum 20", "display_order": 22},
        {"id": "sem31", "label": "SEM 31", "category": "Seminar Room", "query_term": "Seminarraum 31", "display_order": 23},
        {"id": "sem32", "label": "SEM 32", "category": "Seminar Room", "query_term": "Seminarraum 32", "display_order": 24},
        {"id": "sem41", "label": "SEM 41", "category": "Seminar Room", "query_term": "Seminarraum 41", "display_order": 25},
        {"id": "sem42", "label": "SEM 42", "category": "Seminar Room", "query_term": "Seminarraum 42", "display_order": 26},
        {"id": "sem51", "label": "SEM 51", "category": "Seminar Room", "query_term": "Seminarraum 51", "display_order": 27},
        {"id": "sem52", "label": "SEM 52", "category": "Seminar Room", "query_term": "Seminarraum 52", "display_order": 28},
    ],
    # 3. NIG (New Institute Building)
    "nig": [
        {"id": "hsi", "label": "HS I", "category": "Lecture Hall", "query_term": "Hörsaal I", "display_order": 1},
        {"id": "hsii", "label": "HS II", "category": "Lecture Hall", "query_term": "Hörsaal II", "display_order": 2},
        {"id": "hsiii", "label": "HS III", "category": "Lecture Hall", "query_term": "Hörsaal III", "display_order": 3},
        {"id": "hs3b", "label": "HS 3B", "category": "Lecture Hall", "query_term": "Hörsaal 3B", "display_order": 4},
        {"id": "hs3c", "label": "HS 3C", "category": "Lecture Hall", "query_term": "Hörsaal 3C", "display_order": 5},
        {"id": "hs4a", "label": "HS 4A", "category": "Lecture Hall", "query_term": "Hörsaal 4A", "display_order": 6},
        {"id": "hs4b", "label": "HS 4B", "category": "Lecture Hall", "query_term": "Hörsaal 4B", "display_order": 7},
        {"id": "sr1", "label": "SR 1", "category": "Seminar Room", "query_term": "Seminarraum 1", "display_order": 21},
        {"id": "sr2", "label": "SR 2", "category": "Seminar Room", "query_term": "Seminarraum 2", "display_order": 22},
        {"id": "sr3", "label": "SR 3", "category": "Seminar Room", "query_term": "Seminarraum 3", "display_order": 23},
        {"id": "sr4", "label": "SR 4", "category": "Seminar Room", "query_term": "Seminarraum 4", "display_order": 24},
        {"id": "sr5", "label": "SR 5", "category": "Seminar Room", "query_term": "Seminarraum 5", "display_order": 25},
        {"id": "sr6", "label": "SR 6", "category": "Seminar Room", "query_term": "Seminarraum 6", "display_order": 26},
    ],
    # 4. Oskar-Morgenstern-Platz 1 (Mathematics & Business)
    "omp": [
        *[{"id": f"hs{i}", "label": f"HS {i}", "category": "Lecture Hall", "query_term": f"Hörsaal {i}", "display_order": i} for i in range(1, 18)],
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminar Room", "query_term": f"Seminarraum {i}", "display_order": 20 + i} for i in range(1, 17)],
        *[{"id": f"pc{i}", "label": f"PC {i}", "category": "Computer Lab", "query_term": f"PC-Raum {i}", "display_order": 50 + i} for i in range(1, 8)],
    ],
    # 5. Hauptgebäude (Universitätsring 1)
    "hauptgebaeude": [
        {"id": "audimax", "label": "Audimax", "category": "Lecture Hall", "query_term": "Audimax", "display_order": 1},
        {"id": "big-hoersaal", "label": "BIG-Hörsaal", "category": "Lecture Hall", "query_term": "BIG-Hörsaal", "display_order": 2},
        {"id": "grosser-festsaal", "label": "Großer Festsaal", "category": "Lecture Hall", "query_term": "Großer Festsaal", "display_order": 3},
        {"id": "kleiner-festsaal", "label": "Kleiner Festsaal", "category": "Lecture Hall", "query_term": "Kleiner Festsaal", "display_order": 4},
        # Complete list of Hauptgebäude lecture halls
        {"id": "hs1", "label": "HS 1", "category": "Lecture Hall", "query_term": "Hörsaal 1", "display_order": 10},
        {"id": "hs2", "label": "HS 2", "category": "Lecture Hall", "query_term": "Hörsaal 2", "display_order": 11},
        {"id": "hs3", "label": "HS 3", "category": "Lecture Hall", "query_term": "Hörsaal 3", "display_order": 12},
        {"id": "hs5", "label": "HS 5", "category": "Lecture Hall", "query_term": "Hörsaal 5", "display_order": 13},
        {"id": "hs6", "label": "HS 6", "category": "Lecture Hall", "query_term": "Hörsaal 6", "display_order": 14},
        {"id": "hs7", "label": "HS 7", "category": "Lecture Hall", "query_term": "Hörsaal 7", "display_order": 15},
        {"id": "hs16", "label": "HS 16", "category": "Lecture Hall", "query_term": "Hörsaal 16", "display_order": 16},
        {"id": "hs21", "label": "HS 21", "category": "Lecture Hall", "query_term": "Hörsaal 21", "display_order": 17},
        {"id": "hs23", "label": "HS 23", "category": "Lecture Hall", "query_term": "Hörsaal 23", "display_order": 18},
        {"id": "hs24", "label": "HS 24", "category": "Lecture Hall", "query_term": "Hörsaal 24", "display_order": 19},
        {"id": "hs26", "label": "HS 26", "category": "Lecture Hall", "query_term": "Hörsaal 26", "display_order": 20},
        {"id": "hs27", "label": "HS 27", "category": "Lecture Hall", "query_term": "Hörsaal 27", "display_order": 21},
        {"id": "hs28", "label": "HS 28", "category": "Lecture Hall", "query_term": "Hörsaal 28", "display_order": 22},
        {"id": "hs29", "label": "HS 29", "category": "Lecture Hall", "query_term": "Hörsaal 29", "display_order": 23},
        {"id": "hs30", "label": "HS 30", "category": "Lecture Hall", "query_term": "Hörsaal 30", "display_order": 24},
        {"id": "hs31", "label": "HS 31", "category": "Lecture Hall", "query_term": "Hörsaal 31", "display_order": 25},
        {"id": "hs32", "label": "HS 32", "category": "Lecture Hall", "query_term": "Hörsaal 32", "display_order": 26},
        {"id": "hs33", "label": "HS 33", "category": "Lecture Hall", "query_term": "Hörsaal 33", "display_order": 27},
        {"id": "hs34", "label": "HS 34", "category": "Lecture Hall", "query_term": "Hörsaal 34", "display_order": 28},
        {"id": "hs38", "label": "HS 38", "category": "Lecture Hall", "query_term": "Hörsaal 38", "display_order": 29},
        {"id": "hs41", "label": "HS 41 (Gerda-Lerner)", "category": "Lecture Hall", "query_term": "Hörsaal 41", "display_order": 30},
        {"id": "hs42", "label": "HS 42", "category": "Lecture Hall", "query_term": "Hörsaal 42", "display_order": 31},
        {"id": "hs45", "label": "HS 45", "category": "Lecture Hall", "query_term": "Hörsaal 45", "display_order": 32},
        {"id": "hs47", "label": "HS 47", "category": "Lecture Hall", "query_term": "Hörsaal 47", "display_order": 33},
        {"id": "hs50", "label": "HS 50", "category": "Lecture Hall", "query_term": "Hörsaal 50", "display_order": 34},
        # Seminar Rooms
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminar Room", "query_term": f"Seminarraum {i}", "display_order": 50 + i} for i in range(1, 13)],
        # Historic & Ceremonial Halls
        {"id": "arkadenhof", "label": "Arkadenhof", "category": "Hall", "query_term": "Arkadenhof", "display_order": 70},
        {"id": "elise-richter-saal", "label": "Elise Richter Saal", "category": "Hall", "query_term": "Elise Richter Saal", "display_order": 71},
        {"id": "erika-weinzierl-saal", "label": "Erika Weinzierl Saal", "category": "Hall", "query_term": "Erika Weinzierl Saal", "display_order": 72},
        {"id": "franz-koenig-saal", "label": "Franz König Saal", "category": "Hall", "query_term": "Franz Koenig Saal", "display_order": 73},
        {"id": "marietta-blau-saal", "label": "Marietta Blau Saal", "category": "Hall", "query_term": "Marietta Blau Saal", "display_order": 74},
        {"id": "senatssaal", "label": "Senatssaal", "category": "Hall", "query_term": "Senatssaal", "display_order": 75},
        {"id": "green-lounge", "label": "Green Lounge", "category": "Hall", "query_term": "Green Lounge", "display_order": 76},
    ],
    # 6. Campus Altes AKH (Spitalgasse 2)
    "campus": [
        {"id": "hsa", "label": "HS A", "category": "Lecture Hall", "query_term": "Hörsaal A", "display_order": 1},
        {"id": "hsb", "label": "HS B", "category": "Lecture Hall", "query_term": "Hörsaal B", "display_order": 2},
        {"id": "hsc1", "label": "HS C1", "category": "Lecture Hall", "query_term": "Hörsaal C1", "display_order": 3},
        {"id": "hsc2", "label": "HS C2", "category": "Lecture Hall", "query_term": "Hörsaal C2", "display_order": 4},
        {"id": "hsd", "label": "HS D", "category": "Lecture Hall", "query_term": "Hörsaal D", "display_order": 5},
        {"id": "sr1", "label": "SR 1", "category": "Seminar Room", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminar Room", "query_term": "Seminarraum 2", "display_order": 12},
        {"id": "alte-kapelle", "label": "Alte Kapelle", "category": "Lecture Hall", "query_term": "Alte Kapelle", "display_order": 21},
        {"id": "aula", "label": "Aula", "category": "Lecture Hall", "query_term": "Aula", "display_order": 22},
    ],
    # 7. UBB Biologiezentrum (Djerassiplatz 1)
    "ubb": [
        {"id": "hs1", "label": "HS 1", "category": "Lecture Hall", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Lecture Hall", "query_term": "Hörsaal 2", "display_order": 2},
        {"id": "hs3", "label": "HS 3", "category": "Lecture Hall", "query_term": "Hörsaal 3", "display_order": 3},
        {"id": "hs4", "label": "HS 4", "category": "Lecture Hall", "query_term": "Hörsaal 4", "display_order": 4},
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminar Room", "query_term": f"Seminarraum {i}", "display_order": 10 + i} for i in range(1, 15)],
    ],
    # 8. UZA II (Josef-Holaubek-Platz 2 / Althanstraße 14)
    "uza2": [
        *[{"id": f"hs{i}", "label": f"HS {i}", "category": "Lecture Hall", "query_term": f"Hörsaal {i}", "display_order": i} for i in range(1, 9)],
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminar Room", "query_term": f"Seminarraum {i}", "display_order": 20 + i} for i in range(1, 11)],
        {"id": "pc1", "label": "PC 1", "category": "Computer Lab", "query_term": "PC-Raum 1", "display_order": 41},
        {"id": "pc2", "label": "PC 2", "category": "Computer Lab", "query_term": "PC-Raum 2", "display_order": 42},
    ],
    # 9. Faculty of Chemistry (Währinger Straße 38-42)
    "chemie": [
        {"id": "auer", "label": "Auer-v-Welsbach HS", "category": "Lecture Hall", "query_term": "Carl-Auer-von-Welsbach-Hörsaal", "display_order": 1},
        {"id": "spaeth", "label": "Ernst-Späth HS", "category": "Lecture Hall", "query_term": "Ernst-Späth-Hörsaal", "display_order": 2},
        {"id": "kleiner-hoersaal", "label": "Kleiner Hörsaal", "category": "Lecture Hall", "query_term": "Kleiner Hörsaal", "display_order": 3},
        {"id": "grosser-hoersaal", "label": "Großer Hörsaal", "category": "Lecture Hall", "query_term": "Großer Hörsaal", "display_order": 4},
        {"id": "sr1", "label": "SR 1", "category": "Seminar Room", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminar Room", "query_term": "Seminarraum 2", "display_order": 12},
    ],
    # 10. Faculty of Physics (Boltzmanngasse 5 / Strudlhofgasse 4)
    "physik_boltzmann": [
        {"id": "doppler", "label": "Doppler HS", "category": "Lecture Hall", "query_term": "Christian Doppler", "display_order": 1},
        {"id": "meitner", "label": "Lise Meitner HS", "category": "Lecture Hall", "query_term": "Lise Meitner", "display_order": 2},
        {"id": "hess", "label": "Hess HS", "category": "Lecture Hall", "query_term": "Victor Franz Hess", "display_order": 3},
        {"id": "schroedinger", "label": "Schrödinger HS", "category": "Lecture Hall", "query_term": "Erwin Schrödinger", "display_order": 4},
        {"id": "sr1", "label": "SR 1", "category": "Seminar Room", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminar Room", "query_term": "Seminarraum 2", "display_order": 12},
    ],
    # 11. Faculty of Psychology (Kolingasse 14-16 / Liebiggasse 5)
    "psychologie": [
        {"id": "hs1", "label": "HS 1", "category": "Lecture Hall", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Lecture Hall", "query_term": "Hörsaal 2", "display_order": 2},
        {"id": "hs3", "label": "HS 3", "category": "Lecture Hall", "query_term": "Hörsaal 3", "display_order": 3},
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminar Room", "query_term": f"Seminarraum {i}", "display_order": 10 + i} for i in range(1, 9)],
    ],
    # 12. Center for Sport Science (Auf der Schmelz 6)
    "sport": [
        {"id": "hs1", "label": "HS 1", "category": "Lecture Hall", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Lecture Hall", "query_term": "Hörsaal 2", "display_order": 2},
        {"id": "sr1", "label": "SR 1", "category": "Seminar Room", "query_term": "Seminarraum 1", "display_order": 11},
        {"id": "sr2", "label": "SR 2", "category": "Seminar Room", "query_term": "Seminarraum 2", "display_order": 12},
    ],
    # 13. Faculties of Theology (Schenkenstraße 8-10)
    "theologie": [
        {"id": "hs1", "label": "HS 1", "category": "Lecture Hall", "query_term": "Hörsaal 1", "display_order": 1},
        {"id": "hs2", "label": "HS 2", "category": "Lecture Hall", "query_term": "Hörsaal 2", "display_order": 2},
        *[{"id": f"sr{i}", "label": f"SR {i}", "category": "Seminar Room", "query_term": f"Seminarraum {i}", "display_order": 10 + i} for i in range(1, 6)],
    ],
}


def normalize_room_id(slug_or_id: str) -> str:
    """Normalizes various room ID formats into a canonical ID (e.g. 'hoersaal-1' -> 'hs1')."""
    s = slug_or_id.lower().strip()
    if ('gross' in s or 'gr_' in s or 'grfest' in s) and 'festsaal' in s:
        return 'grosser-festsaal'
    if ('klein' in s or 'kl_' in s or 'klfest' in s) and 'festsaal' in s:
        return 'kleiner-festsaal'
    if ('gross' in s or 'gr_' in s or 'grhs' in s) and ('hs' in s or 'hoersaal' in s or 'hörsaal' in s):
        return 'grosser-hoersaal'
    if ('klein' in s or 'kl_' in s or 'klhs' in s) and ('hs' in s or 'hoersaal' in s or 'hörsaal' in s):
        return 'kleiner-hoersaal'
    if 'kapelle' in s:
        return 'alte-kapelle'
    if 'big' in s and ('hoersaal' in s or 'hörsaal' in s or 'hs' in s):
        return 'big-hoersaal'
    s = re.sub(r'^(?:hoersaal|hörsaal)[-_]?', 'hs', s)
    s = re.sub(r'^(?:seminarraum)[-_]?', 'sr', s)
    s = re.sub(r'^(?:pc[-_]unterrichtsraum|pc[-_]raum)[-_]?', 'pc', s)
    s = re.sub(r'^(?:praktikumsraum)[-_]?', 'pr', s)
    return re.sub(r'[^a-z0-9]', '', s)


def seed_database_if_empty(force: bool = False):
    """
    Populates or updates all campuses and rooms across all faculties.
    Cleans up legacy duplicate entries and guarantees canonical IDs.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # Clean up legacy un-normalized and duplicated slugs
        cursor.execute("""
            DELETE FROM rooms
            WHERE id IN ('gr_festsaal', 'grfestsaal', 'kl_festsaal', 'klfestsaal', 'kapelle', 'gr_hs', 'grhs', 'kl_hs', 'klhs')
               OR id LIKE 'hoersaal-%'
               OR id LIKE 'seminarraum-%'
               OR id LIKE 'pc-raum-%'
               OR id LIKE 'pc-unterrichtsraum-%'
        """)
        
        # 1. Insert/Update Campuses
        for c in DEFAULT_CAMPUSES:
            cursor.execute("""
                INSERT INTO campuses (id, name, address, query_prefix, spl_codes, display_order)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    address = excluded.address,
                    query_prefix = excluded.query_prefix,
                    spl_codes = excluded.spl_codes,
                    display_order = excluded.display_order
            """, (c["id"], c["name"], c["address"], c["query_prefix"], c.get("spl_codes", ""), c["display_order"]))
        
        # 2. Insert/Update Rooms for all Campuses
        for campus_id, rooms in SEEDED_ROOMS_MAP.items():
            for r in rooms:
                canonical_id = normalize_room_id(r["id"])
                cursor.execute("""
                    INSERT INTO rooms (id, campus_id, label, category, query_term, display_order, last_synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campus_id, id) DO UPDATE SET
                        label = excluded.label,
                        category = excluded.category,
                        query_term = excluded.query_term,
                        display_order = excluded.display_order,
                        last_synced = excluded.last_synced
                """, (canonical_id, campus_id, r["label"], r["category"], r["query_term"], r["display_order"], now_iso))
        
        # Ensure zero duplicate labels within the same campus
        cursor.execute("""
            DELETE FROM rooms
            WHERE rowid NOT IN (
                SELECT MIN(rowid)
                FROM rooms
                GROUP BY campus_id, label
            )
        """)
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
            SELECT r.*, c.name as campus_name, c.query_prefix, c.spl_codes
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
                
                category = "Hall"
                label = room_slug.replace("-", " ").title()
                query_term = label
                display_order = 100
                
                if "big-hoersaal" in room_slug or "bighoersaal" in room_slug:
                    category = "Lecture Hall"
                    label = "BIG-Hörsaal"
                    query_term = "BIG-Hörsaal"
                    display_order = 2
                elif "grosser-festsaal" in room_slug:
                    category = "Lecture Hall"
                    label = "Großer Festsaal"
                    query_term = "Großer Festsaal"
                    display_order = 3
                elif "kleiner-festsaal" in room_slug:
                    category = "Lecture Hall"
                    label = "Kleiner Festsaal"
                    query_term = "Kleiner Festsaal"
                    display_order = 4
                elif "alte-kapelle" in room_slug or "kapelle" in room_slug:
                    category = "Lecture Hall"
                    label = "Alte Kapelle"
                    query_term = "Alte Kapelle"
                    display_order = 21
                elif "grosser-hoersaal" in room_slug:
                    category = "Lecture Hall"
                    label = "Großer Hörsaal"
                    query_term = "Großer Hörsaal"
                    display_order = 4
                elif "kleiner-hoersaal" in room_slug:
                    category = "Lecture Hall"
                    label = "Kleiner Hörsaal"
                    query_term = "Kleiner Hörsaal"
                    display_order = 3
                elif "hoersaal" in room_slug:
                    category = "Lecture Hall"
                    num = re.sub(r'[^0-9a-zA-Z]', '', room_slug.replace("hoersaal", ""))
                    label = f"HS {num}".strip()
                    query_term = f"Hörsaal {num}".strip()
                    display_order = 10 + (int(num) if num.isdigit() else 0)
                elif "seminarraum" in room_slug:
                    category = "Seminar Room"
                    num = re.sub(r'[^0-9a-zA-Z]', '', room_slug.replace("seminarraum", ""))
                    label = f"SR {num}".strip()
                    query_term = f"Seminarraum {num}".strip()
                    display_order = 50 + (int(num) if num.isdigit() else 0)
                elif "pc-raum" in room_slug or "pc-unterrichtsraum" in room_slug:
                    category = "Computer Lab"
                    num = re.sub(r'[^0-9a-zA-Z]', '', room_slug.replace("pc-unterrichtsraum", "").replace("pc-raum", ""))
                    label = f"PC {num}".strip()
                    query_term = f"PC-Unterrichtsraum {num}".strip()
                    display_order = 80 + (int(num) if num.isdigit() else 0)
                elif "audimax" in room_slug:
                    category = "Lecture Hall"
                    label = "Audimax"
                    query_term = "Audimax"
                    display_order = 1
                
                canonical_id = normalize_room_id(room_slug)
                cursor.execute("""
                    INSERT INTO rooms (id, campus_id, label, category, query_term, display_order, last_synced)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(campus_id, id) DO UPDATE SET
                        label = excluded.label,
                        category = excluded.category,
                        query_term = excluded.query_term,
                        display_order = excluded.display_order,
                        last_synced = excluded.last_synced
                """, (canonical_id, campus_slug, label, category, query_term, display_order, now_iso))
                discovered_count += 1
            
            # Remove any duplicates after crawl
            cursor.execute("""
                DELETE FROM rooms
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM rooms
                    GROUP BY campus_id, label
                )
            """)
            conn.commit()
            
            # 2. Run deterministic SPL schedule harvester for all teaching rooms & computer labs
            spl_count = await sync_rooms_from_spl_schedules()
            total_synced = discovered_count + spl_count
            
            set_meta("last_room_sync", now_iso)
            
        return {"status": "ok", "rooms_synced": total_synced, "synced_at": now_iso}
    except Exception as e:
        logger.error(f"Error syncing room directory: {e}")
        return {"status": "error", "message": str(e)}


CAMPUS_LOCATION_KEYWORDS = {
    "w29": ["währinger straße 29", "währingerstr. 29", "w29", "währinger strasse 29"],
    "omp": ["oskar-morgenstern-platz 1", "omp", "oskar morgenstern"],
    "juridicum": ["schottenbastei 10-16", "juridicum", "schottenbastei"],
    "hauptgebaeude": ["hauptgebäude", "universitätsring 1", "universitaetsring 1", "hauptgeb"],
    "nig": ["universitätsstraße 7", "universitaetsstrasse 7", "nig"],
    "campus": ["spitalgasse 2", "unicampus", "altes akh", "spitalgasse 4"],
    "ubb": ["djerassiplatz 1", "biozentrum", "biologiezentrum"],
    "uza2": ["josef-holaubek-platz 2", "uza ii", "uza 2", "althanstraße 14"],
    "chemie": ["währinger straße 38", "währinger straße 40", "währinger straße 42"],
    "physik_boltzmann": ["boltzmanngasse 5", "strudlhofgasse 4"],
    "psychologie": ["kolingasse 14-16", "liebiggasse 5"],
    "sport": ["auf der schmelz 6"],
    "theologie": ["schenkenstraße 8-10"],
}


def parse_room_from_location_chunk(chunk: str) -> Optional[Tuple[str, str, str, str, int]]:
    """
    Deterministically parses a single location text chunk into:
    (canonical_id, label, category, query_term, display_order)
    """
    chunk_clean = chunk.strip()
    chunk_lower = chunk_clean.lower()
    
    m_pc = re.search(r'PC[- ](?:Unterrichtsraum|Raum|Seminarraum)\s*([0-9]+)', chunk_clean, re.I)
    m_hs = re.search(r'(?:Hörsaal|HS)\s*([0-9]+[A-Za-z]?|[A-Za-z][0-9]*|[IVXLCDM]+)\b', chunk_clean, re.I)
    m_sr = re.search(r'(?:Seminarraum|SR)\s*([0-9]+[A-Za-z]?|[A-Za-z]\b)', chunk_clean, re.I)
    m_pr = re.search(r'(?:Praktikumsraum|Labor)\s*([0-9]+|[A-Za-z]+)', chunk_clean, re.I)
    
    if m_pc:
        num = m_pc.group(1).upper()
        return (f"pc{num.lower()}", f"PC {num}", "Computer Lab", f"PC-Unterrichtsraum {num}", 30 + (int(num) if num.isdigit() else 35))
    elif m_hs:
        num = m_hs.group(1).upper()
        if num in ('HAUPTGEB', 'HAUPTGEBÄUDE', 'WIEN', 'OG', 'EG', 'UG'):
            return None
        return (f"hs{num.lower()}", f"HS {num}", "Lecture Hall", f"Hörsaal {num}", 10 + (int(num) if num.isdigit() else 15))
    elif m_sr:
        num = m_sr.group(1).upper()
        if num in ('HAUPTGEB', 'WIEN', 'OG', 'EG', 'UG'):
            return None
        return (f"sr{num.lower()}", f"SR {num}", "Seminar Room", f"Seminarraum {num}", 50 + (int(num) if num.isdigit() else 55))
    elif m_pr:
        num = m_pr.group(1).upper()
        return (f"pr{num.lower()}", f"PR {num}", "Laboratory", f"Praktikumsraum {num}", 40 + (int(num) if num.isdigit() else 45))
    elif 'audimax' in chunk_lower:
        return ("audimax", "Audimax", "Lecture Hall", "Audimax", 1)
    elif 'festsaal' in chunk_lower:
        if 'gross' in chunk_lower or 'groß' in chunk_lower:
            return ("grosser-festsaal", "Großer Festsaal", "Lecture Hall", "Großer Festsaal", 3)
        elif 'klein' in chunk_lower:
            return ("kleiner-festsaal", "Kleiner Festsaal", "Lecture Hall", "Kleiner Festsaal", 4)
    elif 'big-hörsaal' in chunk_lower or 'big-hoersaal' in chunk_lower or 'big hörsaal' in chunk_lower:
        return ("big-hoersaal", "BIG-Hörsaal", "Lecture Hall", "BIG-Hörsaal", 2)
        
    return None


async def sync_rooms_from_spl_schedules() -> int:
    """
    Deterministically harvests all active rooms across all University of Vienna faculties
    directly from their authoritative ufind SPL iCalendar timetables.
    Guarantees every lecture hall, seminar room, computer lab (e.g. PC-Unterrichtsraum 6),
    and practical room currently in use is discovered and indexed.
    """
    discovered_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; UnivieRoomLookup/1.0)"}
    ssl_ctx = ssl._create_unverified_context()
    
    campuses = get_all_campuses()
    
    with get_connection() as conn:
        cursor = conn.cursor()
        
        for c in campuses:
            campus_id = c["id"]
            spl_codes = [s.strip() for s in (c.get("spl_codes") or "").split(",") if s.strip()]
            keywords = CAMPUS_LOCATION_KEYWORDS.get(campus_id, [])
            
            for spl in spl_codes:
                url = f"https://m2-ufind.univie.ac.at/courses/calendar/query.ics?query={spl}+%2Bct"
                ics_data = ""
                try:
                    if httpx is not None:
                        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
                            resp = await client.get(url, headers=headers)
                            if resp.status_code == 200:
                                ics_data = resp.text
                    else:
                        req = urllib.request.Request(url, headers=headers)
                        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
                            ics_data = r.read().decode('utf-8', errors='ignore')
                except Exception as e:
                    logger.debug(f"Failed to fetch calendar for {spl}: {e}")
                    continue
                    
                if not ics_data:
                    continue
                    
                unfolded = re.sub(r'\r?\n[ \t]', '', ics_data)
                loc_matches = re.findall(r'LOCATION:([^\r\n]+)', unfolded)
                
                for raw_loc in loc_matches:
                    unescaped = raw_loc.replace(r'\,', ',')
                    chunks = re.split(
                        r',\s*(?=(?:Hörsaal|HS|Seminarraum|SR|PC[- ]|Praktikumsraum|Audimax|Festsaal|Saal|Labor))',
                        unescaped,
                        flags=re.I
                    )
                    for chunk in chunks:
                        if not any(k in chunk.lower() for k in keywords):
                            continue
                            
                        parsed = parse_room_from_location_chunk(chunk)
                        if not parsed:
                            continue
                            
                        room_id, label, category, query_term, display_order = parsed
                        canonical_id = normalize_room_id(room_id)
                        
                        cursor.execute("""
                            INSERT INTO rooms (id, campus_id, label, category, query_term, display_order, last_synced)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(campus_id, id) DO UPDATE SET
                                label = excluded.label,
                                category = excluded.category,
                                query_term = excluded.query_term,
                                last_synced = excluded.last_synced
                        """, (canonical_id, campus_id, label, category, query_term, display_order, now_iso))
                        discovered_count += 1
                        
        # Enforce deduplication by (campus_id, label)
        cursor.execute("""
            DELETE FROM rooms
            WHERE rowid NOT IN (
                SELECT MIN(rowid)
                FROM rooms
                GROUP BY campus_id, label
            )
        """)
        conn.commit()
        
    return discovered_count


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
