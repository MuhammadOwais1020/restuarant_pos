function showAlert(type, message) {
  let alertEl = document.createElement("div");
  alertEl.className = `alert ${type}`;
  alertEl.innerHTML = `<i class="fa ${
    type === "success" ? "fa-check-circle" : "fa-exclamation-circle"
  }"></i>${message}`;
  document.body.appendChild(alertEl);
  setTimeout(() => alertEl.classList.add("show"), 10);
  setTimeout(() => {
    alertEl.classList.remove("show");
    setTimeout(() => document.body.removeChild(alertEl), 300);
  }, 3000);
}
