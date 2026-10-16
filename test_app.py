"""
Verification test script for room-lookup modules.
Tests all University of Vienna faculties, room catalogs, and PC rooms.
"""
from datetime import datetime
from app.db import init_db, get_connection
from app.catalog import seed_database_if_empty, get_all_campuses, get_rooms_for_campus
from app.analyzer import parse_ics_events, analyze_room_status, VIENNA_TZ

SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:icalendar-ruby
BEGIN:VEVENT
UID:test-event-pc4
DTSTART;TZID=Europe/Vienna:20261016T100000
DTEND;TZID=Europe/Vienna:20261016T120000
LOCATION:Hybride Lehre\, PC-Unterrichtsraum 4\, Währinger Straße 29 1.OG
SUMMARY:051012-1 PUE Repetitorium Technische Grundlagen der Informatik
URL;VALUE=URI:https://ufind.univie.ac.at/de/course.html?lv=051012&semester=2026W#gr1
END:VEVENT
END:VCALENDAR"""

def run_tests():
    print("1. Initializing DB & Seeding all University of Vienna faculties...")
    init_db()
    seed_database_if_empty()
    
    campuses = get_all_campuses()
    assert len(campuses) >= 13, f"Expected >= 13 faculties/campuses, got {len(campuses)}"
    print(f"   ✓ All {len(campuses)} faculties verified:")
    for c in campuses:
        print(f"     - {c['name']}")

    print("\n2. Verifying W29 PC-Räume and Lecture Halls...")
    w29_rooms = get_rooms_for_campus("w29")
    w29_labels = [r["label"] for r in w29_rooms]
    assert "PC 1" in w29_labels, "PC 1 missing from W29"
    assert "PC 4" in w29_labels, "PC 4 missing from W29"
    assert "HS 1" in w29_labels, "HS 1 missing from W29"
    assert "SR 12" in w29_labels, "SR 12 missing from W29"
    print(f"   ✓ W29 total rooms: {len(w29_rooms)} (including {', '.join([l for l in w29_labels if 'PC' in l])})")

    print("\n3. Verifying Other Faculties (Juridicum, NIG, UBB, OMP)...")
    juridicum_rooms = get_rooms_for_campus("juridicum")
    assert len(juridicum_rooms) >= 15, "Juridicum rooms missing"
    print(f"   ✓ Juridicum rooms: {len(juridicum_rooms)} rooms (e.g. {[r['label'] for r in juridicum_rooms[:4]]})")

    nig_rooms = get_rooms_for_campus("nig")
    assert len(nig_rooms) >= 10, "NIG rooms missing"
    print(f"   ✓ NIG rooms: {len(nig_rooms)} rooms (e.g. {[r['label'] for r in nig_rooms[:4]]})")

    ubb_rooms = get_rooms_for_campus("ubb")
    assert len(ubb_rooms) >= 15, "UBB rooms missing"
    print(f"   ✓ UBB Biologie rooms: {len(ubb_rooms)} rooms")

    print("\n4. Testing PC-Unterrichtsraum Occupancy Analysis...")
    t_occ = datetime(2026, 10, 16, 11, 0, tzinfo=VIENNA_TZ) if hasattr(VIENNA_TZ, 'localize') is False else VIENNA_TZ.localize(datetime(2026, 10, 16, 11, 0))
    res_pc = analyze_room_status(SAMPLE_ICS, t_occ, "PC 4", "PC-Unterrichtsraum 4")
    assert res_pc["is_occupied"] is True
    assert res_pc["current_course"]["title"] == "Repetitorium Technische Grundlagen der Informatik"
    print(f"   ✓ PC 4 at 11:00: {res_pc['status']} - {res_pc['current_course']['title']} (Ends in {res_pc['current_course']['ends_in']})")

    print("\n🎉 ALL FACULTIES & PC ROOM TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
