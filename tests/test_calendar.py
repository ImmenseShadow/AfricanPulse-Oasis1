import unittest

from tests.test_routes import WebTestCase


class CalendarRouteTests(WebTestCase):
    def item_data(self, **changes):
        return {
            "kind": "event", "title": "BOS editorial meeting", "description": "Weekly review",
            "start_at": "2026-11-04T09:30", "end_at": "2026-11-04T10:30",
            "all_day": "0", "location": "Communications room", "category": "Meeting",
            "color": "blue", "status": "planned", "notes": "Bring the draft",
            "reminder_minutes": "15", **changes,
        }

    def test_calendar_views_and_create_persistence(self):
        response = self.post("/calendar/new", self.item_data(), follow_redirects=True)
        self.assertIn(b"BOS editorial meeting", response.data)
        self.assertEqual(self.client.get("/calendar").status_code, 200)
        for view in ("month", "week", "day", "agenda"):
            self.assertEqual(self.client.get(f"/calendar?view={view}&date=2026-11-04").status_code, 200)
        page = self.client.get("/calendar?view=day&date=2026-11-04").data
        self.assertIn(b"BOS editorial meeting", page)
        self.assertIn(b"09:30", page)

    def test_validation_edit_status_and_delete(self):
        bad = self.post("/calendar/new", self.item_data(end_at="2026-11-04T08:30"))
        self.assertEqual(bad.status_code, 400)
        self.assertIn(b"end time must be after", bad.data)
        malformed = self.post("/calendar/new", self.item_data(start_at="2026-11-04"))
        self.assertEqual(malformed.status_code, 400)
        self.assertIn(b"Enter valid start and end", malformed.data)
        self.post("/calendar/new", self.item_data(kind="schedule", reminder_minutes=""))
        from src.storage.calendar_repository import CalendarRepository
        repo = CalendarRepository(self.db)
        item = repo.list_between("2026-11-04T00:00", "2026-11-05T00:00")[0]
        edited = self.post(f"/calendar/{item['id']}/edit", self.item_data(
            kind="schedule", title="Updated review", reminder_minutes=""), follow_redirects=True)
        self.assertIn(b"Updated review", edited.data)
        self.assertEqual(self.post(f"/calendar/{item['id']}/status", {"status": "completed"}).status_code, 302)
        self.assertEqual(repo.get(item["id"])["status"], "completed")
        self.assertEqual(self.post(f"/calendar/{item['id']}/delete").status_code, 302)
        self.assertIsNone(repo.get(item["id"]))

    def test_calendar_posts_require_csrf(self):
        response = self.client.post("/calendar/new", data=self.item_data())
        self.assertEqual(response.status_code, 400)

    def test_dashboard_upcoming_items_come_from_calendar_storage(self):
        from src.storage.calendar_repository import CalendarRepository
        CalendarRepository(self.db).create({
            "kind": "schedule", "title": "Dashboard schedule check", "description": "",
            "start_at": "2099-06-10T09:00", "end_at": "2099-06-10T10:00", "all_day": 0,
            "location": "", "category": "Editorial", "color": "green", "status": "planned",
            "notes": "", "reminder_minutes": None,
        })
        self.assertIn(b"Dashboard schedule check", self.client.get("/").data)


if __name__ == "__main__":
    unittest.main()