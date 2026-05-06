import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from typing import Optional

from db import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_OVERDUE,
    STATUS_PENDING,
    Reminder,
    ReminderRepository,
)

try:
    from win10toast import ToastNotifier
except Exception:
    ToastNotifier = None


DATETIME_FORMAT = "%d-%m-%Y %H:%M"


class ReminderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Напоминалка Windows 11")
        self.root.geometry("1160x700")

        self.repo = ReminderRepository()
        self.repo.init_db()

        self.toast = ToastNotifier() if ToastNotifier else None

        self.filter_var = tk.StringVar(value="Все")
        self.title_var = tk.StringVar()
        self.description_var = tk.StringVar()
        self.datetime_var = tk.StringVar(value=datetime.now().strftime(DATETIME_FORMAT))
        self.recurrence_var = tk.StringVar(value="Без повтора")
        self.by_date_day_var = tk.StringVar(value=str(datetime.now().day))
        self.yearly_day_var = tk.StringVar(value=f"{datetime.now().day:02d}")
        self.yearly_month_var = tk.StringVar(value=f"{datetime.now().month:02d}")
        self.stats_var = tk.StringVar(value="Всего: 0 | Ожидает: 0 | Готово: 0 | Просрочено: 0")
        self.weekday_vars = {
            "Пн": tk.BooleanVar(value=False),
            "Вт": tk.BooleanVar(value=False),
            "Ср": tk.BooleanVar(value=False),
            "Чт": tk.BooleanVar(value=False),
            "Пт": tk.BooleanVar(value=False),
            "Сб": tk.BooleanVar(value=False),
            "Вс": tk.BooleanVar(value=False),
        }

        self._build_ui()
        self._load_reminders()
        self._schedule_checks()

    def _build_ui(self) -> None:
        ttk.Label(
            self.root,
            text="Напоминалка",
            font=("Segoe UI", 28, "bold"),
        ).pack(pady=(14, 8))

        top = ttk.LabelFrame(self.root, text="Добавить новое напоминание")
        top.pack(fill="x", padx=20, pady=(0, 12))

        ttk.Label(top, text="Заголовок:").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(top, textvariable=self.title_var).grid(row=0, column=1, columnspan=5, sticky="ew", padx=10, pady=8)

        ttk.Label(top, text="Описание:").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(top, textvariable=self.description_var).grid(row=1, column=1, columnspan=5, sticky="ew", padx=10, pady=8)

        ttk.Label(top, text="Дата и время:").grid(row=2, column=0, sticky="w", padx=10, pady=8)
        ttk.Button(top, text="Через 1 мин", command=lambda: self._set_quick_time(1)).grid(row=2, column=1, sticky="w", padx=4, pady=6)
        ttk.Button(top, text="Через 5 мин", command=lambda: self._set_quick_time(5)).grid(row=2, column=2, sticky="w", padx=4, pady=6)
        ttk.Button(top, text="Через 15 мин", command=lambda: self._set_quick_time(15)).grid(row=2, column=3, sticky="w", padx=4, pady=6)
        ttk.Button(top, text="Через 1 час", command=lambda: self._set_quick_time(60)).grid(row=2, column=4, sticky="w", padx=4, pady=6)

        ttk.Entry(top, textvariable=self.datetime_var).grid(row=3, column=1, columnspan=5, sticky="ew", padx=10, pady=(0, 8))

        ttk.Label(top, text="Повтор:").grid(row=4, column=0, sticky="w", padx=10, pady=8)
        recurrence_combo = ttk.Combobox(
            top,
            textvariable=self.recurrence_var,
            state="readonly",
            values=[
                "Без повтора",
                "По дням недели",
                "По дате",
                "Каждый месяц",
                "Каждый год",
            ],
        )
        recurrence_combo.grid(row=4, column=1, columnspan=2, sticky="w", padx=10, pady=8)
        recurrence_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_recurrence_controls())

        weekday_frame = ttk.Frame(top)
        weekday_frame.grid(row=4, column=3, columnspan=3, sticky="w", padx=4, pady=8)
        self.weekday_checks: list[ttk.Checkbutton] = []
        for i, (label, var) in enumerate(self.weekday_vars.items()):
            check = ttk.Checkbutton(weekday_frame, text=label, variable=var)
            check.grid(row=0, column=i, padx=2)
            self.weekday_checks.append(check)

        recurrence_extra = ttk.Frame(top)
        recurrence_extra.grid(row=5, column=0, columnspan=6, sticky="w", padx=10, pady=(0, 4))
        ttk.Label(recurrence_extra, text="Для 'По дате' число:").pack(side="left")
        self.by_date_day_entry = ttk.Entry(recurrence_extra, textvariable=self.by_date_day_var, width=5)
        self.by_date_day_entry.pack(side="left", padx=(6, 14))
        ttk.Label(recurrence_extra, text="Для 'Каждый год' день/месяц:").pack(side="left")
        self.yearly_day_entry = ttk.Entry(recurrence_extra, textvariable=self.yearly_day_var, width=5)
        self.yearly_day_entry.pack(side="left", padx=(6, 4))
        ttk.Label(recurrence_extra, text="/").pack(side="left")
        self.yearly_month_entry = ttk.Entry(recurrence_extra, textvariable=self.yearly_month_var, width=5)
        self.yearly_month_entry.pack(side="left", padx=(4, 4))

        actions = ttk.Frame(top)
        actions.grid(row=6, column=0, columnspan=6, pady=(6, 10))
        ttk.Button(actions, text="Добавить напоминание", command=self._on_add).pack(side="left", padx=8)
        ttk.Button(actions, text="Тест уведомления", command=self._test_notification).pack(side="left", padx=8)

        for col in range(1, 6):
            top.columnconfigure(col, weight=1)
        self._update_recurrence_controls()

        controls = ttk.Frame(self.root)
        controls.pack(fill="x", padx=20, pady=(0, 8))
        ttk.Label(controls, text="Фильтр по статусу:").pack(side="left")

        status_combo = ttk.Combobox(
            controls,
            textvariable=self.filter_var,
            state="readonly",
            values=["Все", STATUS_PENDING, STATUS_DONE, STATUS_OVERDUE, STATUS_CANCELLED],
            width=16,
        )
        status_combo.pack(side="left", padx=8)
        status_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_reminders())

        ttk.Button(controls, text="Обновить", command=self._load_reminders).pack(side="left", padx=8)
        ttk.Button(controls, text="Готово", command=lambda: self._on_set_status(STATUS_DONE)).pack(side="left", padx=8)
        ttk.Button(controls, text="Отменено", command=lambda: self._on_set_status(STATUS_CANCELLED)).pack(side="left", padx=8)
        ttk.Button(controls, text="Удалить", command=self._on_delete).pack(side="left", padx=8)
        ttk.Label(controls, textvariable=self.stats_var, font=("Segoe UI", 11, "bold")).pack(side="right")

        list_frame = ttk.LabelFrame(self.root, text="Список напоминаний")
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        columns = ("id", "title", "description", "trigger_at", "recurrence", "status", "created_at")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.tree.heading("id", text="ID")
        self.tree.heading("title", text="Заголовок")
        self.tree.heading("description", text="Описание")
        self.tree.heading("trigger_at", text="Дата/Время")
        self.tree.heading("recurrence", text="Повтор")
        self.tree.heading("status", text="Статус")
        self.tree.heading("created_at", text="Создано")

        self.tree.column("id", width=50, anchor="center")
        self.tree.column("title", width=230)
        self.tree.column("description", width=330)
        self.tree.column("trigger_at", width=150, anchor="center")
        self.tree.column("recurrence", width=140, anchor="center")
        self.tree.column("status", width=140, anchor="center")
        self.tree.column("created_at", width=150, anchor="center")

        self.tree.tag_configure("done", background="#ccefd0")
        self.tree.tag_configure("overdue", background="#f2cccc")
        self.tree.tag_configure("cancelled", background="#e6e6e6")

        y_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=8)
        y_scroll.pack(side="right", fill="y", padx=(0, 6), pady=8)

    def _set_quick_time(self, minutes: int) -> None:
        self.datetime_var.set((datetime.now() + timedelta(minutes=minutes)).strftime(DATETIME_FORMAT))

    def _update_recurrence_controls(self) -> None:
        mode = self.recurrence_var.get()
        weekly_enabled = mode == "По дням недели"
        by_date_enabled = mode == "По дате"
        yearly_enabled = mode == "Каждый год"

        weekly_state = "normal" if weekly_enabled else "disabled"
        for check in self.weekday_checks:
            check.configure(state=weekly_state)
        if not weekly_enabled:
            for var in self.weekday_vars.values():
                var.set(False)

        self.by_date_day_entry.configure(state="normal" if by_date_enabled else "disabled")
        self.yearly_day_entry.configure(state="normal" if yearly_enabled else "disabled")
        self.yearly_month_entry.configure(state="normal" if yearly_enabled else "disabled")

    def _update_stats(self) -> None:
        counts = self.repo.status_counts()
        total = sum(counts.values())
        self.stats_var.set(
            f"Всего: {total} | Ожидает: {counts[STATUS_PENDING]} | "
            f"Готово: {counts[STATUS_DONE]} | Просрочено: {counts[STATUS_OVERDUE]}"
        )

    def _row_tag(self, status: str) -> str:
        if status == STATUS_DONE:
            return "done"
        if status == STATUS_OVERDUE:
            return "overdue"
        if status == STATUS_CANCELLED:
            return "cancelled"
        return ""

    def _load_reminders(self) -> None:
        self.repo.mark_overdue()
        for item in self.tree.get_children():
            self.tree.delete(item)

        reminders = self.repo.list_reminders(self.filter_var.get())
        for reminder in reminders:
            self.tree.insert(
                "",
                "end",
                values=(
                    reminder.reminder_id,
                    reminder.title,
                    reminder.description,
                    reminder.trigger_at.strftime(DATETIME_FORMAT),
                    self._format_recurrence(reminder),
                    reminder.status,
                    reminder.created_at.strftime(DATETIME_FORMAT),
                ),
                tags=(self._row_tag(reminder.status),),
            )
        self._update_stats()

    def _format_recurrence(self, reminder: Reminder) -> str:
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

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        try:
            return datetime.strptime(value.strip(), DATETIME_FORMAT)
        except ValueError:
            return None

    def _on_add(self) -> None:
        title = self.title_var.get().strip()
        description = self.description_var.get().strip()
        trigger_dt = self._parse_datetime(self.datetime_var.get())

        if not title:
            messagebox.showerror("Ошибка", "Введите заголовок напоминания.")
            return
        if not description:
            messagebox.showerror("Ошибка", "Введите описание напоминания.")
            return
        if not trigger_dt:
            messagebox.showerror("Ошибка", "Неверный формат даты/времени. Пример: 06-05-2026 22:30")
            return

        try:
            recurrence_type, recurrence_value = self._build_recurrence(trigger_dt)
        except ValueError as exc:
            messagebox.showerror("Ошибка", str(exc))
            return
        if recurrence_type == "weekly" and not recurrence_value:
            messagebox.showerror("Ошибка", "Для повтора по дням недели выберите хотя бы один день.")
            return

        self.repo.add_reminder(
            title=title,
            description=description,
            trigger_at=trigger_dt,
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
        )
        self.title_var.set("")
        self.description_var.set("")
        self.datetime_var.set(datetime.now().strftime(DATETIME_FORMAT))
        self.recurrence_var.set("Без повтора")
        self.by_date_day_var.set(str(datetime.now().day))
        self.yearly_day_var.set(f"{datetime.now().day:02d}")
        self.yearly_month_var.set(f"{datetime.now().month:02d}")
        for var in self.weekday_vars.values():
            var.set(False)
        self._update_recurrence_controls()
        self._load_reminders()

    def _build_recurrence(self, trigger_dt: datetime) -> tuple[str, str]:
        selected = self.recurrence_var.get()
        if selected == "По дням недели":
            indexes = [str(i) for i, var in enumerate(self.weekday_vars.values()) if var.get()]
            return "weekly", ",".join(indexes)
        if selected == "По дате":
            day = self._parse_int(self.by_date_day_var.get())
            if day is None or not (1 <= day <= 31):
                raise ValueError("Введите число месяца от 1 до 31 для режима 'По дате'.")
            return "by_date", str(day)
        if selected == "Каждый месяц":
            return "monthly", ""
        if selected == "Каждый год":
            day = self._parse_int(self.yearly_day_var.get())
            month = self._parse_int(self.yearly_month_var.get())
            if day is None or month is None:
                raise ValueError("Для режима 'Каждый год' укажите день и месяц цифрами.")
            if not (1 <= day <= 31 and 1 <= month <= 12):
                raise ValueError("Для режима 'Каждый год': день 1-31, месяц 1-12.")
            return "yearly", f"{day:02d}-{month:02d}"
        return "none", ""

    @staticmethod
    def _parse_int(value: str) -> Optional[int]:
        try:
            return int(value.strip())
        except ValueError:
            return None

    def _selected_id(self) -> Optional[int]:
        selected = self.tree.selection()
        if not selected:
            return None
        return int(self.tree.item(selected[0], "values")[0])

    def _on_delete(self) -> None:
        reminder_id = self._selected_id()
        if reminder_id is None:
            messagebox.showwarning("Внимание", "Выберите напоминание в таблице.")
            return
        if messagebox.askyesno("Подтверждение", "Удалить выбранное напоминание?"):
            self.repo.delete_reminder(reminder_id)
            self._load_reminders()

    def _on_set_status(self, status: str) -> None:
        reminder_id = self._selected_id()
        if reminder_id is None:
            messagebox.showwarning("Внимание", "Выберите напоминание в таблице.")
            return
        self.repo.update_status(reminder_id, status)
        self._load_reminders()

    def _show_due_popup(self, reminder: Reminder) -> None:
        popup = tk.Toplevel(self.root)
        popup.title(f"Напоминание: {reminder.title}")
        popup.attributes("-topmost", True)
        popup.geometry("450x250")
        popup.grab_set()

        ttk.Label(popup, text=reminder.title, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Label(popup, text=f"Время: {reminder.trigger_at.strftime(DATETIME_FORMAT)}").pack(anchor="w", padx=12)

        body = tk.Text(popup, height=8, wrap="word")
        body.insert("1.0", reminder.description)
        body.configure(state="disabled")
        body.pack(fill="both", expand=True, padx=12, pady=8)

        ttk.Button(popup, text="Закрыть", command=popup.destroy).pack(pady=(0, 12))
        popup.lift()
        popup.focus_force()

    def _show_notification(self, reminder: Reminder) -> None:
        if self.toast:
            threading.Thread(
                target=self.toast.show_toast,
                kwargs={
                    "title": f"Напоминание: {reminder.title}",
                    "msg": reminder.description[:250],
                    "duration": 10,
                    "threaded": True,
                },
                daemon=True,
            ).start()

    def _test_notification(self) -> None:
        test_reminder = Reminder(
            reminder_id=-1,
            title="Тест уведомления",
            description="Проверка отображения системного уведомления и popup.",
            trigger_at=datetime.now(),
            created_at=datetime.now(),
            status=STATUS_PENDING,
            notified=False,
            recurrence_type="none",
            recurrence_value="",
        )
        self._show_notification(test_reminder)
        self._show_due_popup(test_reminder)

    def _check_due_reminders(self) -> None:
        due = self.repo.due_reminders()
        for reminder in due:
            self._show_notification(reminder)
            self._show_due_popup(reminder)
            self.repo.handle_triggered(reminder)

        self.repo.mark_overdue()
        self._load_reminders()

    def _schedule_checks(self) -> None:
        self._check_due_reminders()
        self.root.after(20_000, self._schedule_checks)


def main() -> None:
    root = tk.Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    ReminderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
