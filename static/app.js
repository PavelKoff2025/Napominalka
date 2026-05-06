const triggerInput = document.getElementById("trigger-at");
const quickButtons = document.querySelectorAll(".quick-buttons button");
const recurrenceSelect = document.getElementById("recurrence");
const weekdaysWrap = document.getElementById("weekdays-wrap");
const byDateWrap = document.getElementById("by-date-wrap");
const yearlyWrap = document.getElementById("yearly-wrap");
const weekdaysInput = document.getElementById("weekdays-input");

const dueDialog = document.getElementById("due-dialog");
const dueTitle = document.getElementById("due-title");
const dueTime = document.getElementById("due-time");
const dueDescription = document.getElementById("due-description");
const dueClose = document.getElementById("due-close");

function pad(value) {
  return value.toString().padStart(2, "0");
}

function formatDate(date) {
  return `${pad(date.getDate())}-${pad(date.getMonth() + 1)}-${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function setDefaultTrigger() {
  if (!triggerInput.value.trim()) {
    triggerInput.value = formatDate(new Date());
  }
}

function updateRecurrenceControls() {
  const mode = recurrenceSelect.value;
  weekdaysWrap.classList.toggle("hidden", mode !== "weekly");
  byDateWrap.classList.toggle("hidden", mode !== "by_date");
  yearlyWrap.classList.toggle("hidden", mode !== "yearly");
}

function updateWeekdaysInput() {
  const selected = Array.from(weekdaysWrap.querySelectorAll("input[type=checkbox]:checked"))
    .map((item) => item.value);
  weekdaysInput.value = selected.join(",");
}

async function fetchDue() {
  const response = await fetch("/api/due");
  if (!response.ok) return;
  const reminders = await response.json();
  for (const item of reminders) {
    showDuePopup(item);
    await notifyBrowser(item);
    await fetch(`/api/due/${item.id}/ack`, { method: "POST" });
  }
  if (reminders.length > 0) {
    window.location.reload();
  }
}

function showDuePopup(item) {
  dueTitle.textContent = item.title;
  dueTime.textContent = `Время: ${item.trigger_at}`;
  dueDescription.textContent = item.description;
  dueDialog.showModal();
}

async function notifyBrowser(item) {
  if (!("Notification" in window)) return;

  if (Notification.permission === "default") {
    await Notification.requestPermission();
  }
  if (Notification.permission === "granted") {
    new Notification(`Напоминание: ${item.title}`, {
      body: item.description,
    });
  }
}

quickButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const minutes = Number(button.dataset.minutes);
    const target = new Date(Date.now() + minutes * 60 * 1000);
    triggerInput.value = formatDate(target);
  });
});

recurrenceSelect.addEventListener("change", updateRecurrenceControls);
weekdaysWrap.querySelectorAll("input[type=checkbox]").forEach((item) => {
  item.addEventListener("change", updateWeekdaysInput);
});

dueClose.addEventListener("click", () => {
  dueDialog.close();
});

setDefaultTrigger();
updateRecurrenceControls();
updateWeekdaysInput();
setInterval(fetchDue, 15000);
