const state = { rows: [] };

const elements = {
  amountPaid: document.querySelector("#amountPaid"),
  connectionStatus: document.querySelector("#connectionStatus"),
  emptyMessage: document.querySelector("#emptyMessage"),
  errorMessage: document.querySelector("#errorMessage"),
  flaggedOrders: document.querySelector("#flaggedOrders"),
  lastUpdated: document.querySelector("#lastUpdated"),
  outstandingBalance: document.querySelector("#outstandingBalance"),
  refreshButton: document.querySelector("#refreshButton"),
  reportRows: document.querySelector("#reportRows"),
  searchInput: document.querySelector("#searchInput"),
  statusFilter: document.querySelector("#statusFilter"),
  totalOrders: document.querySelector("#totalOrders"),
};

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function setText(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

function renderSummary(rows) {
  const sum = (field) => rows.reduce((total, row) => total + Number(row[field] || 0), 0);
  const count = (status) => rows.filter((row) => row.financial_status === status).length;

  elements.totalOrders.textContent = rows.length.toLocaleString();
  elements.amountPaid.textContent = money.format(sum("amount_paid"));
  elements.outstandingBalance.textContent = money.format(sum("outstanding_balance"));
  elements.flaggedOrders.textContent = rows.filter((row) => row.discrepancy_flags).length.toLocaleString();
  setText("unpaidCount", count("unpaid"));
  setText("partialCount", count("partial"));
  setText("paidCount", count("paid"));
  setText("overpaidCount", count("overpaid"));
}

function buildCell(value, className = "") {
  const cell = document.createElement("td");
  cell.textContent = value;
  if (className) cell.className = className;
  return cell;
}

function renderRows() {
  const query = elements.searchInput.value.trim().toLowerCase();
  const selectedStatus = elements.statusFilter.value;
  const rows = state.rows.filter((row) => {
    const matchesSearch = !query
      || String(row.order_id).includes(query)
      || row.name.toLowerCase().includes(query);
    const matchesStatus = selectedStatus === "all"
      || row.financial_status === selectedStatus
      || (selectedStatus === "flagged" && row.discrepancy_flags);
    return matchesSearch && matchesStatus;
  });

  elements.reportRows.replaceChildren();
  elements.emptyMessage.hidden = rows.length !== 0;

  rows.forEach((row) => {
    const tableRow = document.createElement("tr");
    tableRow.append(buildCell(`#${row.order_id}`, "order-id"));

    const customerCell = document.createElement("td");
    const customerName = document.createElement("span");
    customerName.className = "customer-name";
    customerName.textContent = row.name;
    const customerId = document.createElement("span");
    customerId.className = "customer-id";
    customerId.textContent = `Customer ${row.customer_id}`;
    customerCell.append(customerName, customerId);
    tableRow.append(customerCell);

    tableRow.append(buildCell(money.format(Number(row.total))));
    tableRow.append(buildCell(money.format(Number(row.amount_paid))));
    tableRow.append(buildCell(money.format(Number(row.outstanding_balance))));
    tableRow.append(buildCell(row.payment_count));

    const statusCell = document.createElement("td");
    const statusPill = document.createElement("span");
    statusPill.className = `pill ${row.financial_status}`;
    statusPill.textContent = row.financial_status;
    statusCell.append(statusPill);
    tableRow.append(statusCell);

    tableRow.append(buildCell(row.discrepancy_flags || "Clear", row.discrepancy_flags ? "flag" : "clear"));
    elements.reportRows.append(tableRow);
  });
}

async function loadDashboard() {
  elements.refreshButton.disabled = true;
  elements.connectionStatus.textContent = "Refreshing";
  elements.connectionStatus.className = "connection";
  elements.errorMessage.hidden = true;

  try {
    const response = await fetch("/reconciliation", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(response.status === 503 ? "Database is unavailable. Configure DATABASE_URL and load data before using the dashboard." : `Request failed with status ${response.status}.`);

    state.rows = await response.json();
    renderSummary(state.rows);
    renderRows();
    elements.connectionStatus.textContent = "Live data";
    elements.connectionStatus.className = "connection online";
    elements.lastUpdated.textContent = `Updated ${new Date().toLocaleString()}`;
  } catch (error) {
    elements.connectionStatus.textContent = "Unavailable";
    elements.connectionStatus.className = "connection offline";
    elements.errorMessage.textContent = error.message;
    elements.errorMessage.hidden = false;
    elements.lastUpdated.textContent = "Data could not be refreshed";
  } finally {
    elements.refreshButton.disabled = false;
  }
}

elements.refreshButton.addEventListener("click", loadDashboard);
elements.searchInput.addEventListener("input", renderRows);
elements.statusFilter.addEventListener("change", renderRows);
loadDashboard();
