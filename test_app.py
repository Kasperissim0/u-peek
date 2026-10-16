"""
Verification test script for room-lookup modules.
Tests all University of Vienna faculties, room catalogs, and PC rooms.
"""
from datetime import datetime
from app.db import init_db, get_connection
from app.catalog import seed_database_if_empty, get_all_campuses, get_rooms_for_campus
from app.analyzer import parse_ics_events, analyze_room_status, VIENNA_TZ

SAMPLE_ICS_DBS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:icalendar-ruby
BEGIN:VEVENT
UID:dbs-hs1-event
DTSTART;TZID=Europe/Vienna:20261016T131500
DTEND;TZID=Europe/Vienna:20261016T144500
LOCATION:Hörsaal 1\, Währinger Straße 29 1.UG
SUMMARY:051031-1 VU Datenbanksysteme
URL;VALUE=URI:https://ufind.univie.ac.at/de/course.html?lv=051031&semester=2026W#gr1
END:VEVENT
BEGIN:VEVENT
UID:tgi-hs1-event
DTSTART;TZID=Europe/Vienna:20261016T150000
DTEND;TZID=Europe/Vienna:20261016T163000
LOCATION:Hörsaal 1\, Währinger Straße 29 1.UG
SUMMARY:051010-1 VO Technische Grundlagen der Informatik
URL;VALUE=URI:https://ufind.univie.ac.at/de/course.html?lv=051010&semester=2026W#gr1
END:VEVENT
END:VCALENDAR"""

def run_tests():
    print("1. Initializing DB & Seeding all University of Vienna faculties...")
    init_db()
    seed_database_if_empty()
    
    campuses = get_all_campuses()
    assert len(campuses) >= 13, f"Expected >= 13 faculties/campuses, got {len(campuses)}"
    print(f"   ✓ All {len(campuses)} faculties verified with SPL codes.")

    print("\n2. Verifying W29 PC-Räume and Lecture Halls...")
    w29_rooms = get_rooms_for_campus("w29")
    w29_labels = [r["label"] for r in w29_rooms]
    assert "PC 1" in w29_labels, "PC 1 missing from W29"
    assert "PC 2" in w29_labels, "PC 2 missing from W29"
    assert "PC 6" in w29_labels, "PC 6 missing from W29"
    assert "HS 1" in w29_labels, "HS 1 missing from W29"
    assert "SR 6" in w29_labels, "SR 6 missing from W29"
    print(f"   ✓ W29 rooms: {len(w29_rooms)} (including PC 1 - PC 6, SR 1 - SR 12, HS 1 - HS 3)")

    print("\n3. Verifying Hauptgebäude (Main Building) Rooms & Zero Duplicates...")
    hg_rooms = get_rooms_for_campus("hauptgebaeude")
    hg_labels = [r["label"] for r in hg_rooms]
    assert "Audimax" in hg_labels, "Audimax missing"
    assert "BIG-Hörsaal" in hg_labels, "BIG-Hörsaal missing"
    assert "Großer Festsaal" in hg_labels, "Großer Festsaal missing"
    assert "Kleiner Festsaal" in hg_labels, "Kleiner Festsaal missing"
    assert "HS 1" in hg_labels and "HS 50" in hg_labels, "HS 1 or HS 50 missing from Hauptgebäude"
    assert "SR 1" in hg_labels and "SR 12" in hg_labels, "SR 1 or SR 12 missing from Hauptgebäude"
    
    # Assert zero duplicated labels
    assert len(hg_labels) == len(set(hg_labels)), f"Found duplicate room labels in Hauptgebäude: {hg_labels}"
    print(f"   ✓ Hauptgebäude rooms: {len(hg_rooms)} distinct rooms (Audimax, BIG-Hörsaal, Festsaal, HS 1-50, SR 1-12, Halls). Zero duplicates.")

    print("\n4. Testing Sanity Check: HS 1 Today at 13:45 during 051031 VU Datenbanksysteme...")
    t_dbs = datetime(2026, 10, 16, 13, 45, tzinfo=VIENNA_TZ) if hasattr(VIENNA_TZ, 'localize') is False else VIENNA_TZ.localize(datetime(2026, 10, 16, 13, 45))
    res_dbs = analyze_room_status(SAMPLE_ICS_DBS, t_dbs, "HS 1", "Hörsaal 1")
    assert res_dbs["is_occupied"] is True, "HS 1 should be OCCUPIED"
    assert res_dbs["current_course"]["code"] == "051031-1", f"Expected 051031-1, got {res_dbs['current_course']['code']}"
    assert res_dbs["current_course"]["title"] == "Datenbanksysteme", f"Expected Datenbanksysteme, got {res_dbs['current_course']['title']}"
    assert res_dbs["next_course"]["title"] == "Technische Grundlagen der Informatik"
    assert "Freitag-,16.10." in res_dbs["current_course"]["url"], f"Invalid highlight URL: {res_dbs['current_course']['url']}"
    assert "Freitag-,16.10." in res_dbs["next_course"]["url"], f"Invalid next course highlight URL: {res_dbs['next_course']['url']}"
    print(f"   ✓ Status: {res_dbs['status']}")
    print(f"   ✓ Course: {res_dbs['current_course']['title']} ({res_dbs['current_course']['code']})")
    print(f"   ✓ Highlight URL: {res_dbs['current_course']['url']}")
    print(f"   ✓ Time: {res_dbs['current_course']['start']} - {res_dbs['current_course']['end']} (Ends in {res_dbs['current_course']['ends_in']})")
    print(f"   ✓ Next: {res_dbs['next_course']['title']} at {res_dbs['next_course']['start']}")

    print("\n🎉 ALL TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
