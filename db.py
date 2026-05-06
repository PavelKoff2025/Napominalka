import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Iterator, List, Optional


DB_FILENAME = "reminders.db"

STATUS_PENDING = "Ожидает"
STATUS_DONE = "Готово"
STATUS_OVERDUE = "Просрочено"
STATUS_CANCELLED = "Отменено"

VALID_STATUSES = {
    STATUS_PENDING,
    STATUS_DONE,
    STATUS_OVERDUE,
    STATUS_CANCELLED,
}


@dataclass
class Reminder:
    reminder_id: int
    title: str
    description: str
    trigger_at: datetime
    created_at: datetime
    status: str
    notified: bool
    recurrence_type: str
    recurrence_value: str


class ReminderRepository:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else Path(DB_FILENAME)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    trigger_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('Ожидает', 'Готово', 'Просрочено', 'Отменено')),
                    notified INTEGER NOT NULL DEFAULT 0,
                    recurrence_type TEXT NOT NULL DEFAULT 'none',
                    recurrence_value TEXT NOT NULL DEFAULT ''
                )
                """
            )
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(reminders)").fetchall()
            }
            if "created_at" not in columns:
                conn.execute("ALTER TABLE reminders ADD COLUMN created_at TEXT")
                conn.execute(
                    """
                    UPDATE reminders
                    SET created_at = trigger_at
                    WHERE created_at IS NULL OR created_at = ''
                    """
                )
            if "recurrence_type" not in columns:
                conn.execute("ALTER TABLE reminders ADD COLUMN recurrence_type TEXT NOT NULL DEFAULT 'none'")
            if "recurrence_value" not in columns:
                conn.execute("ALTER TABLE reminders ADD COLUMN recurrence_value TEXT NOT NULL DEFAULT ''")

    def add_reminder(
        self,
        title: str,
        description: str,
        trigger_at: datetime,
        recurrence_type: str = "none",
        recurrence_value: str = "",
    ) -> int:
        with self._connect() as conn:
            now_str = datetime.now().isoformat(timespec="seconds")
            cursor = conn.execute(
                """
                INSERT INTO reminders (
                    title,
                    description,
                    trigger_at,
                    created_at,
                    status,
                    notified,
                    recurrence_type,
                    recurrence_value
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    title,
                    description,
                    trigger_at.isoformat(timespec="seconds"),
                    now_str,
                    STATUS_PENDING,
                    recurrence_type,
                    recurrence_value,
                ),
            )
            return int(cursor.lastrowid)

    def delete_reminder(self, reminder_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    def get_reminder(self, reminder_id: int) -> Optional[Reminder]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reminders WHERE id = ?",
                (reminder_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_reminder(row)

    def update_status(self, reminder_id: int, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Unsupported status: {status}")

        with self._connect() as conn:
            conn.execute(
                "UPDATE reminders SET status = ? WHERE id = ?",
                (status, reminder_id),
            )

    def mark_notified(self, reminder_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE reminders SET notified = 1 WHERE id = ?",
                (reminder_id,),
            )

    def list_reminders(self, status: Optional[str] = None) -> List[Reminder]:
        query = "SELECT * FROM reminders"
        params = ()
        if status and status != "Все":
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY datetime(trigger_at) ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_reminder(row) for row in rows]

    def mark_overdue(self, now: Optional[datetime] = None) -> int:
        current_time = now or datetime.now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE reminders
                SET status = ?
                WHERE status = ?
                  AND datetime(trigger_at) < datetime(?)
                """,
                (STATUS_OVERDUE, STATUS_PENDING, current_time.isoformat(timespec="seconds")),
            )
            return cursor.rowcount

    def due_reminders(self, now: Optional[datetime] = None) -> List[Reminder]:
        current_time = now or datetime.now()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reminders
                WHERE status = ?
                  AND notified = 0
                  AND datetime(trigger_at) <= datetime(?)
                ORDER BY datetime(trigger_at) ASC
                """,
                (STATUS_PENDING, current_time.isoformat(timespec="seconds")),
            ).fetchall()
            return [self._row_to_reminder(row) for row in rows]

    def status_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*) as cnt
                FROM reminders
                GROUP BY status
                """
            ).fetchall()

        counts = {
            STATUS_PENDING: 0,
            STATUS_DONE: 0,
            STATUS_OVERDUE: 0,
            STATUS_CANCELLED: 0,
        }
        for row in rows:
            counts[str(row["status"])] = int(row["cnt"])
        return counts

    def handle_triggered(self, reminder: Reminder) -> None:
        if reminder.recurrence_type == "none":
            self.mark_notified(reminder.reminder_id)
            return

        next_trigger = self._calculate_next_trigger(reminder)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE reminders
                SET trigger_at = ?, status = ?, notified = 0
                WHERE id = ?
                """,
                (
                    next_trigger.isoformat(timespec="seconds"),
                    STATUS_PENDING,
                    reminder.reminder_id,
                ),
            )

    @staticmethod
    def _calculate_next_trigger(reminder: Reminder) -> datetime:
        current = reminder.trigger_at
        now = datetime.now()

        if reminder.recurrence_type == "weekly":
            weekdays = [
                int(x) for x in reminder.recurrence_value.split(",")
                if x.strip().isdigit()
            ]
            weekdays = sorted(set(day for day in weekdays if 0 <= day <= 6))
            if not weekdays:
                return now

            base_date = now.date()
            for offset in range(0, 14):
                candidate_date = base_date + timedelta(days=offset)
                if candidate_date.weekday() not in weekdays:
                    continue
                candidate = datetime.combine(candidate_date, current.time())
                if candidate > now:
                    return candidate
            return now

        if reminder.recurrence_type == "by_date":
            target_day = int(reminder.recurrence_value or current.day)
            year = now.year
            month = now.month
            while True:
                days = ReminderRepository._days_in_month(year, month)
                day = min(target_day, days)
                candidate = datetime(year, month, day, current.hour, current.minute, current.second)
                if candidate > now:
                    return candidate
                if month == 12:
                    month = 1
                    year += 1
                else:
                    month += 1

        if reminder.recurrence_type == "monthly":
            target_day = current.day
            year = now.year
            month = now.month
            while True:
                days = ReminderRepository._days_in_month(year, month)
                day = min(target_day, days)
                candidate = datetime(year, month, day, current.hour, current.minute, current.second)
                if candidate > now:
                    return candidate
                if month == 12:
                    month = 1
                    year += 1
                else:
                    month += 1

        if reminder.recurrence_type == "yearly":
            month_day = (reminder.recurrence_value or "").split("-")
            if len(month_day) == 2 and month_day[0].isdigit() and month_day[1].isdigit():
                target_day = int(month_day[0])
                target_month = int(month_day[1])
            else:
                target_day = current.day
                target_month = current.month

            year = now.year
            while True:
                days = ReminderRepository._days_in_month(year, target_month)
                day = min(target_day, days)
                candidate = datetime(year, target_month, day, current.hour, current.minute, current.second)
                if candidate > now:
                    return candidate
                year += 1

        return now

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        if month == 12:
            next_month = date(year + 1, 1, 1)
        else:
            next_month = date(year, month + 1, 1)
        this_month = date(year, month, 1)
        return (next_month - this_month).days

    @staticmethod
    def _row_to_reminder(row: sqlite3.Row) -> Reminder:
        created_value = row["created_at"]
        created_dt = (
            datetime.fromisoformat(str(created_value))
            if created_value
            else datetime.fromisoformat(str(row["trigger_at"]))
        )
        return Reminder(
            reminder_id=int(row["id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            trigger_at=datetime.fromisoformat(str(row["trigger_at"])),
            created_at=created_dt,
            status=str(row["status"]),
            notified=bool(row["notified"]),
            recurrence_type=str(row["recurrence_type"] or "none"),
            recurrence_value=str(row["recurrence_value"] or ""),
        )
