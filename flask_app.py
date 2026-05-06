from datetime import datetime
from typing import Optional

from flask import Flask, jsonify, redirect, render_template, request, url_for

from db import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_OVERDUE,
    STATUS_PENDING,
    Reminder,
    ReminderRepository,
)


DATETIME_FORMAT = "%d-%m-%Y %H:%M"
STATUS_FILTERS = ["Все", STATUS_PENDING, STATUS_DONE, STATUS_OVERDUE, STATUS_CANCELLED]

app = Flask(__name__)
repo = ReminderRepository()
repo.init_db()


def parse_datetime(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value.strip(), DATETIME_FORMAT)
    except ValueError:
        return None


def recurrence_label(reminder: Reminder) -> str:
    if reminder.recurrence_type == "weekly":
        names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        selected = []
        for token in reminder.recurrence_value.split(","):
            token = token.strip()
            if token.isdigit() and 0 <= int(token) <= 6:
                selected.append(names[int(token)])
        return "Еженедельно: " + ", ".join(selected) if selected else "Еженедельно"
    if reminder.recurrence_type == "by_date":
        return f"По дате: {reminder.recurrence_value}"
    if reminder.recurrence_type == "monthly":
        return "Каждый месяц"
    if reminder.recurrence_type == "yearly":
        return "Каждый год"
    return "Без повтора"


def build_recurrence(form_data: dict, trigger_dt: datetime) -> tuple[str, str]:
    mode = form_data.get("recurrence", "none")

    if mode == "weekly":
        selected = form_data.get("weekdays", "")
        if not selected:
            raise ValueError("Выберите хотя бы один день недели.")
        return "weekly", selected

    if mode == "by_date":
        day_raw = form_data.get("by_date_day", "").strip()
        if not day_raw.isdigit():
            raise ValueError("Для повтора по дате укажите число месяца (1-31).")
        day = int(day_raw)
        if day < 1 or day > 31:
            raise ValueError("Число месяца должно быть в диапазоне 1-31.")
        return "by_date", str(day)

    if mode == "monthly":
        return "monthly", ""

    if mode == "yearly":
        day_raw = form_data.get("yearly_day", "").strip()
        month_raw = form_data.get("yearly_month", "").strip()
        if not day_raw.isdigit() or not month_raw.isdigit():
            raise ValueError("Для ежегодного повтора укажите день и месяц числами.")
        day = int(day_raw)
        month = int(month_raw)
        if day < 1 or day > 31 or month < 1 or month > 12:
            raise ValueError("Для ежегодного повтора: день 1-31, месяц 1-12.")
        return "yearly", f"{day:02d}-{month:02d}"

    return "none", ""


@app.get("/")
def index():
    repo.mark_overdue()
    selected_status = request.args.get("status", "Все")
    reminders = repo.list_reminders(selected_status)
    counts = repo.status_counts()
    total = sum(counts.values())
    return render_template(
        "index.html",
        reminders=reminders,
        selected_status=selected_status,
        statuses=STATUS_FILTERS,
        counts=counts,
        total=total,
        datetime_format=DATETIME_FORMAT,
        recurrence_label=recurrence_label,
        error=None,
    )


@app.post("/add")
def add_reminder():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    trigger_at_raw = request.form.get("trigger_at", "")
    trigger_dt = parse_datetime(trigger_at_raw)

    if not title or not description or not trigger_dt:
        return redirect(url_for("index"))

    try:
        recurrence_type, recurrence_value = build_recurrence(request.form, trigger_dt)
    except ValueError:
        return redirect(url_for("index"))

    repo.add_reminder(
        title=title,
        description=description,
        trigger_at=trigger_dt,
        recurrence_type=recurrence_type,
        recurrence_value=recurrence_value,
    )
    return redirect(url_for("index"))


@app.post("/reminders/<int:reminder_id>/delete")
def delete_reminder(reminder_id: int):
    repo.delete_reminder(reminder_id)
    return redirect(url_for("index"))


@app.post("/reminders/<int:reminder_id>/status")
def set_status(reminder_id: int):
    status = request.form.get("status")
    if status in [STATUS_DONE, STATUS_CANCELLED]:
        repo.update_status(reminder_id, status)
    return redirect(url_for("index"))


@app.get("/api/due")
def due_reminders():
    due = repo.due_reminders()
    return jsonify(
        [
            {
                "id": item.reminder_id,
                "title": item.title,
                "description": item.description,
                "trigger_at": item.trigger_at.strftime(DATETIME_FORMAT),
            }
            for item in due
        ]
    )


@app.post("/api/due/<int:reminder_id>/ack")
def ack_due(reminder_id: int):
    reminder = repo.get_reminder(reminder_id)
    if reminder:
        repo.handle_triggered(reminder)
    repo.mark_overdue()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=True)
