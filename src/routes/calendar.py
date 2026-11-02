"""Calendar workspace routes and server-side validation."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from src import deps

bp = Blueprint("calendar", __name__, url_prefix="/calendar")
VIEWS = ("month", "week", "day", "agenda")
CATEGORIES = ("Editorial", "Meeting", "Social media", "Campaign", "Deadline", "Other")
COLORS = ("green", "coral", "blue", "gold", "rose")
STATUSES = ("planned", "in_progress", "completed", "cancelled")
REMINDERS = {"": None, "0": 0, "5": 5, "15": 15, "30": 30, "60": 60, "1440": 1440}
STATUS_LABELS = {
    "planned": "Planned", "in_progress": "In progress", "completed": "Completed", "cancelled": "Cancelled",
}


def _parse_date(value: str | None) -> date:
    try:
        return date.fromisoformat(value) if value else date.today()
    except ValueError:
        return date.today()


def _week_start(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_shift(day: date, amount: int) -> date:
    index = day.year * 12 + day.month - 1 + amount
    year, month = divmod(index, 12)
    return day.replace(year=year, month=month + 1, day=1)


def _short_date(day: date, include_year: bool = False) -> str:
    label = f"{day.strftime('%b')} {day.day}"
    return f"{label}, {day.year}" if include_year else label


def _event_dict(row: dict) -> dict:
    result = dict(row)
    result["start_date"] = result["start_at"][:10]
    result["end_date"] = result["end_at"][:10]
    result["start_time"] = result["start_at"][11:16]
    result["end_time"] = result["end_at"][11:16]
    result["status_label"] = STATUS_LABELS.get(result["status"], result["status"])
    return result


@bp.get("")
def index():
    view = request.args.get("view", "month")
    view = view if view in VIEWS else "month"
    selected = _parse_date(request.args.get("date"))
    if view == "month":
        month_first = _month_start(selected)
        grid_start = _week_start(month_first)
        grid_end = _week_start(_month_shift(month_first, 1) - timedelta(days=1)) + timedelta(days=7)
        start, end = grid_start, grid_end
        days = [start + timedelta(days=i) for i in range((end - start).days)]
        range_label = selected.strftime("%B %Y")
    elif view == "week":
        start = _week_start(selected)
        end = start + timedelta(days=7)
        days = [start + timedelta(days=i) for i in range(7)]
        range_label = f"{_short_date(start)} – {_short_date(end - timedelta(days=1), True)}"
    elif view == "day":
        start, end = selected, selected + timedelta(days=1)
        days = [selected]
        range_label = f"{selected.strftime('%A, %B')} {selected.day}, {selected.year}"
    else:
        start, end = selected, selected + timedelta(days=30)
        days = [start + timedelta(days=i) for i in range((end - start).days)]
        range_label = f"{_short_date(start)} – {_short_date(end - timedelta(days=1), True)}"

    events = [_event_dict(item) for item in deps.calendar().list_between(
        datetime.combine(start, time.min).isoformat(timespec="minutes"),
        datetime.combine(end, time.min).isoformat(timespec="minutes"),
    )]
    events_by_date: dict[str, list[dict]] = {}
    for event in events:
        item_start = date.fromisoformat(event["start_date"])
        item_end = date.fromisoformat(event["end_date"])
        if datetime.fromisoformat(event["end_at"]).time() == time.min and item_end > item_start:
            item_end -= timedelta(days=1)
        cursor = max(item_start, start)
        last_day = min(item_end, end - timedelta(days=1))
        while cursor <= last_day:
            events_by_date.setdefault(cursor.isoformat(), []).append(event)
            cursor += timedelta(days=1)

    previous = selected - timedelta(days=1) if view == "day" else (
        selected - timedelta(days=7) if view == "week" else
        _month_shift(selected, -1) if view == "month" else selected - timedelta(days=30)
    )
    following = selected + timedelta(days=1) if view == "day" else (
        selected + timedelta(days=7) if view == "week" else
        _month_shift(selected, 1) if view == "month" else selected + timedelta(days=30)
    )
    return render_template(
        "calendar.html", view=view, selected=selected, days=days, events=events,
        events_by_date=events_by_date, range_label=range_label, previous=previous,
        following=following, today=date.today(), status_labels=STATUS_LABELS,
    )


def _form_values(item: dict | None = None) -> dict:
    if request.method == "POST":
        form = request.form
        raw_reminder = form.get("reminder_minutes", "")
        return {
            "kind": form.get("kind", "event"), "title": form.get("title", "").strip(),
            "description": form.get("description", "").strip(),
            "start_at": form.get("start_at", ""), "end_at": form.get("end_at", ""),
            "all_day": form.get("all_day") == "1", "location": form.get("location", "").strip(),
            "category": form.get("category", "Other"), "color": form.get("color", "green"),
            "status": form.get("status", "planned"), "notes": form.get("notes", "").strip(),
            "reminder_minutes": raw_reminder,
        }
    if item:
        result = dict(item)
        result["all_day"] = bool(result["all_day"])
        result["reminder_minutes"] = "" if result["reminder_minutes"] is None else str(result["reminder_minutes"])
        return result
    date_value = request.args.get("date", date.today().isoformat())
    selected = _parse_date(date_value)
    return {
        "kind": request.args.get("kind", "event"), "title": "", "description": "",
        "start_at": datetime.combine(selected, time(9)).isoformat(timespec="minutes"),
        "end_at": datetime.combine(selected, time(10)).isoformat(timespec="minutes"),
        "all_day": False, "location": "", "category": "Other", "color": "green",
        "status": "planned", "notes": "", "reminder_minutes": "",
    }


def _validate(form: dict) -> tuple[dict | None, str | None]:
    if form["kind"] not in ("event", "schedule"):
        return None, "Choose event or schedule."
    if not form["title"] or len(form["title"]) > 160:
        return None, "Title is required and must be 160 characters or fewer."
    if len(form["description"]) > 4000 or len(form["notes"]) > 4000:
        return None, "Descriptions and notes must be 4,000 characters or fewer."
    if len(form["location"]) > 200:
        return None, "Location must be 200 characters or fewer."
    if form["category"] not in CATEGORIES or form["color"] not in COLORS:
        return None, "Choose a valid category and colour."
    if form["status"] not in STATUSES:
        return None, "Choose a valid schedule status."
    def parse_local_datetime(value: str) -> datetime:
        for pattern in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, pattern)
            except ValueError:
                continue
        raise ValueError("Invalid local datetime")

    try:
        start = parse_local_datetime(form["start_at"])
        end = parse_local_datetime(form["end_at"])
    except (TypeError, ValueError):
        return None, "Enter valid start and end dates and times."
    if end <= start:
        return None, "The end time must be after the start time."
    raw_reminder = str(form["reminder_minutes"])
    if raw_reminder not in REMINDERS:
        return None, "Choose a valid reminder interval."
    return {
        **form, "start_at": start.isoformat(timespec="minutes"),
        "end_at": end.isoformat(timespec="minutes"),
        "all_day": int(form["all_day"]),
        "reminder_minutes": REMINDERS[raw_reminder],
    }, None


def _render_form(form: dict, item_id: int | None = None, status: int = 200):
    return render_template(
        "calendar_form.html", form=form, item_id=item_id, categories=CATEGORIES,
        colors=COLORS, statuses=STATUSES, status_labels=STATUS_LABELS,
    ), status


@bp.route("/new", methods=["GET", "POST"])
def create():
    form = _form_values()
    if request.method == "POST":
        valid, problem = _validate(form)
        if problem:
            flash(problem, "error")
            return _render_form(form, status=400)
        item_id = deps.calendar().create(valid)
        flash("Schedule saved." if valid["kind"] == "schedule" else "Event saved.", "success")
        return redirect(url_for("calendar.detail", item_id=item_id))
    return _render_form(form)


@bp.get("/<int:item_id>")
def detail(item_id: int):
    item = deps.calendar().get(item_id)
    if item is None:
        abort(404, description="That calendar item was not found.")
    return render_template("calendar_detail.html", item=_event_dict(item), statuses=STATUSES,
                           status_labels=STATUS_LABELS)


@bp.route("/<int:item_id>/edit", methods=["GET", "POST"])
def edit(item_id: int):
    item = deps.calendar().get(item_id)
    if item is None:
        abort(404, description="That calendar item was not found.")
    form = _form_values(item)
    if request.method == "POST":
        valid, problem = _validate(form)
        if problem:
            flash(problem, "error")
            return _render_form(form, item_id, 400)
        deps.calendar().update(item_id, valid)
        flash("Calendar item updated.", "success")
        return redirect(url_for("calendar.detail", item_id=item_id))
    return _render_form(form, item_id)


@bp.post("/<int:item_id>/status")
def update_status(item_id: int):
    status = request.form.get("status", "")
    if status not in STATUSES:
        flash("Choose a valid schedule status.", "error")
    elif not deps.calendar().update_status(item_id, status):
        abort(404, description="That calendar item was not found.")
    else:
        flash("Schedule status updated.", "success")
    return redirect(url_for("calendar.detail", item_id=item_id))


@bp.post("/<int:item_id>/delete")
def delete(item_id: int):
    if not deps.calendar().delete(item_id):
        abort(404, description="That calendar item was not found.")
    flash("Calendar item deleted.", "success")
    return redirect(url_for("calendar.index"))