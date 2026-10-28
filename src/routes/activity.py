from flask import Blueprint, jsonify, render_template

from src import deps

bp = Blueprint("activity", __name__)


@bp.get("/activity")
def index():
    runs = deps.runs()
    return render_template("activity.html", runs=runs.recent_runs(30), running=runs.running_run())


@bp.get("/collect/status")
def status():
    runs = deps.runs()
    running = runs.running_run()
    if running is None:
        return jsonify(running=False)
    return jsonify(
        running=True,
        sources_done=runs.sources_done(running["id"]),
        sources_total=running["sources_attempted"],
    )
