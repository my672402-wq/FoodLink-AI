/**
 * FoodLink AI - Dashboard & Management Modules Controller
 * Covers Dashboard Analytics, Donors, NGOs, Donations, AI Matching, Demand Forecasting & Food Safety
 */

// -------------------------------------------------------------
// 1. MAIN DASHBOARD METRICS & CHARTS
// -------------------------------------------------------------
async function loadDashboardMetrics() {
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();
    if (data.status !== "success") return;

    const m = data.metrics;
    document.getElementById("kpiTotalDonors").textContent = m.total_donors;
    document.getElementById("kpiTotalMeals").textContent = m.total_meals_available;
    document.getElementById("kpiMealsAllocated").textContent = m.meals_allocated;
    document.getElementById("kpiActiveNgos").textContent = m.active_ngos;

    const allocPct = m.total_meals_available > 0 
      ? Math.round((m.meals_allocated / m.total_meals_available) * 100) 
      : 0;
    document.getElementById("kpiAllocatedPct").textContent = `${allocPct}% redistributed`;

    // Urgent Alerts Banner
    const urgentBox = document.getElementById("urgentAlertBox");
    if (data.urgent_donations && data.urgent_donations.length > 0) {
      document.getElementById("urgentAlertCount").textContent = data.urgent_donations.length;
      urgentBox.style.display = "flex";
    } else {
      urgentBox.style.display = "none";
    }

    // Render Charts
    renderCategoryChart(data.category_breakdown);
    renderPipelineChart(m.total_meals_available, m.meals_allocated, m.meals_pending);

    // Render Recent Allocations
    renderRecentAllocations(data.recent_allocations);

    // Load AI Platform Insights
    loadAiPlatformInsights();
  } catch (err) {
    console.error("Error loading dashboard metrics:", err);
  }
}

function renderCategoryChart(categories) {
  const ctx = document.getElementById("categoryChart");
  if (!ctx) return;

  if (window.FoodLink.charts.category) {
    window.FoodLink.charts.category.destroy();
  }

  const labels = categories.map(c => c.food_category);
  const values = categories.map(c => c.meals);

  window.FoodLink.charts.category = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: labels.length ? labels : ["No data"],
      datasets: [{
        data: values.length ? values : [1],
        backgroundColor: [
          "#10b981", "#3b82f6", "#f59e0b", "#8b5cf6", "#ec4899", "#64748b"
        ],
        borderWidth: 2,
        borderColor: "#ffffff"
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "right" }
      }
    }
  });
}

function renderPipelineChart(total, allocated, pending) {
  const ctx = document.getElementById("pipelineChart");
  if (!ctx) return;

  if (window.FoodLink.charts.pipeline) {
    window.FoodLink.charts.pipeline.destroy();
  }

  window.FoodLink.charts.pipeline = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["Total Logged", "Allocated to NGOs", "Pending Matching"],
      datasets: [{
        label: "Meals Volume",
        data: [total, allocated, pending],
        backgroundColor: ["#3b82f6", "#10b981", "#f59e0b"],
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: { beginAtZero: true }
      }
    }
  });
}

function renderRecentAllocations(allocations) {
  const tbody = document.getElementById("recentAllocationsTbody");
  if (!tbody) return;

  if (!allocations || allocations.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding: 24px; color: var(--navy-500);">No allocations dispatched yet. Run AI Matching on a donation to propose allocations.</td></tr>`;
    return;
  }

  tbody.innerHTML = allocations.map(a => {
    const isAccepted = a.status === "Accepted";
    const statusBadge = isAccepted
      ? `<span class="badge badge-success">Accepted</span>`
      : `<span class="badge badge-warning">Proposed</span>`;

    const actionBtn = isAccepted
      ? `<span style="font-size: 12px; color: #166534; font-weight: 600;">✓ Confirmed</span>`
      : `<button class="btn btn-primary btn-sm" onclick="acceptAllocation(${a.id})">Accept Batch</button>`;

    return `
      <tr>
        <td><strong>#AL-${a.id}</strong></td>
        <td><strong>${escapeHtml(a.food_name)}</strong></td>
        <td>${escapeHtml(a.donor_name)}</td>
        <td><strong>${escapeHtml(a.ngo_name)}</strong></td>
        <td><span class="badge badge-info">${a.allocated_meals} meals</span></td>
        <td>${a.distance_km} km</td>
        <td><span class="badge badge-success">${a.matching_score}/100</span></td>
        <td>${statusBadge}</td>
        <td>${actionBtn}</td>
      </tr>
    `;
  }).join("");
}

async function acceptAllocation(allocationId) {
  try {
    const res = await fetch(`/api/allocations/${allocationId}/accept`, { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      showToastNotification("sms", "📱 SMS to Donor", "Donation accepted! Delivery volunteer dispatched for pickup.");
      showToastNotification("dispatch", "🚗 Volunteer Route Activated", "Road navigation dispatch packet sent to volunteer unit.");
      alert("Allocation confirmed! NGO capacity and occupancy updated.");
      loadDashboardMetrics();
      loadDonations();
      loadNgos();
      loadNotificationsFeed(false);
    } else {
      alert("Error: " + data.error);
    }
  } catch (err) {
    alert("Request failed: " + err.message);
  }
}

async function loadAiPlatformInsights() {
  const box = document.getElementById("aiInsightsList");
  if (!box) return;

  const btnRefresh = document.getElementById("btnRefreshAiInsights");
  if (btnRefresh && !btnRefresh.dataset.bound) {
    btnRefresh.addEventListener("click", () => {
      box.innerHTML = `<em>Refreshing operational telemetry & intelligence...</em>`;
      loadAiPlatformInsights();
    });
    btnRefresh.dataset.bound = "true";
  }

  try {
    const res = await fetch("/api/ai-insights", { method: "POST" });
    const data = await res.json();
    const insightsData = data.insights_data || {};
    const insights = insightsData.insights || [];

    const tag = document.getElementById("geminiModelTag");
    if (tag) {
      if (insightsData.ai_powered) {
        tag.className = "badge badge-success";
        tag.textContent = `✨ ${insightsData.model || "Gemini 2.5 Flash"}`;
      } else {
        tag.className = "badge badge-neutral";
        tag.textContent = "⚙️ Rule Engine Analytics";
      }
    }

    box.innerHTML = `
      <ul style="list-style: none; display: flex; flex-direction: column; gap: 8px;">
        ${insights.map(i => `
          <li style="display: flex; gap: 8px; align-items: flex-start;">
            <span style="color: #3b82f6; font-size: 15px;">•</span>
            <span>${escapeHtml(i)}</span>
          </li>
        `).join("")}
      </ul>
    `;
  } catch (err) {
    box.innerHTML = `<em>Failed to load automated insights: ${escapeHtml(err.message)}</em>`;
  }
}

// -------------------------------------------------------------
// 2. DONOR MANAGEMENT
// -------------------------------------------------------------
async function loadDonors() {
  try {
    const res = await fetch("/api/donors");
    const data = await res.json();
    if (data.status !== "success") return;

    window.FoodLink.donors = data.donors;
    const tbody = document.getElementById("donorsTableBody");
    if (!tbody) return;

    if (data.donors.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 20px;">No donors registered yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.donors.map(d => `
      <tr>
        <td>#DN-${d.id}</td>
        <td><strong>${escapeHtml(d.name)}</strong></td>
        <td><span class="badge badge-neutral">${escapeHtml(d.donor_type)}</span></td>
        <td>${escapeHtml(d.contact_name)}</td>
        <td>
          <div>${escapeHtml(d.phone)}</div>
          <small style="color: var(--navy-500);">${escapeHtml(d.email || "")}</small>
        </td>
        <td>${escapeHtml(d.address)}</td>
        <td><code style="font-size: 11px;">${d.latitude.toFixed(4)}, ${d.longitude.toFixed(4)}</code></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Error loading donors:", err);
  }
}

function populateDonorsDropdown(selectId) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  sel.innerHTML = `<option value="">-- Select Registered Donor --</option>` +
    window.FoodLink.donors.map(d => `<option value="${d.id}">${escapeHtml(d.name)} (${d.donor_type})</option>`).join("");
}

// Donor registration form handler
document.addEventListener("DOMContentLoaded", () => {
  const formDonor = document.getElementById("formRegisterDonor");
  if (formDonor) {
    formDonor.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = {
        name: document.getElementById("donorName").value,
        donor_type: document.getElementById("donorType").value,
        contact_name: document.getElementById("donorContact").value,
        phone: document.getElementById("donorPhone").value,
        email: document.getElementById("donorEmail").value,
        address: document.getElementById("donorAddress").value,
        latitude: parseFloat(document.getElementById("donorLat").value),
        longitude: parseFloat(document.getElementById("donorLon").value)
      };

      try {
        const res = await fetch("/api/donors", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.status === "success") {
          showToastNotification("sms", "📱 SMS Dispatched to Donor", `Account '${payload.name}' activated. Verification SMS sent to ${payload.phone}`);
          alert("Donor registered successfully!");
          closeModal("modalDonor");
          formDonor.reset();
          loadDonors();
          loadDashboardMetrics();
          loadNotificationsFeed(false);
        } else {
          alert("Error registering donor: " + result.error);
        }
      } catch (err) {
        alert("Request failed: " + err.message);
      }
    });
  }
});

// -------------------------------------------------------------
// 3. NGO MANAGEMENT
// -------------------------------------------------------------
async function loadNgos() {
  try {
    const res = await fetch("/api/ngos");
    const data = await res.json();
    if (data.status !== "success") return;

    window.FoodLink.ngos = data.ngos;
    const tbody = document.getElementById("ngosTableBody");
    if (!tbody) return;

    if (data.ngos.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding: 20px;">No NGOs registered yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.ngos.map(n => {
      const occPct = Math.round((n.current_occupancy / Math.max(1, n.daily_capacity)) * 100);
      const dietLabels = (n.dietary_preferences || []).map(dp => `<span class="badge badge-neutral" style="font-size:10px;">${dp}</span>`).join(" ");

      return `
        <tr>
          <td>#NG-${n.id}</td>
          <td><strong>${escapeHtml(n.name)}</strong></td>
          <td><span class="badge badge-info">${escapeHtml(n.ngo_type)}</span></td>
          <td>${escapeHtml(n.contact_name)}<br><small style="color:var(--navy-500);">${n.phone}</small></td>
          <td>${escapeHtml(n.address)}</td>
          <td>${n.daily_capacity} meals</td>
          <td>
            <div style="display:flex; align-items:center; gap:8px;">
              <span>${n.current_occupancy} (${occPct}%)</span>
              <div style="width: 50px; height: 5px; background: #e2e8f0; border-radius: 99px; overflow: hidden;">
                <div style="width: ${Math.min(100, occPct)}%; height:100%; background: ${occPct > 80 ? '#ef4444' : '#10b981'};"></div>
              </div>
            </div>
          </td>
          <td><span class="badge badge-success">${n.available_capacity} meals</span></td>
          <td>${dietLabels}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="viewNgoForecast(${n.id})">📈 Forecast</button>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading NGOs:", err);
  }
}

function viewNgoForecast(ngoId) {
  navigateTo("forecasting");
  const sel = document.getElementById("forecastNgoSelect");
  if (sel) {
    sel.value = ngoId;
    loadForecastForSelectedNgo();
  }
}

// NGO registration form handler
document.addEventListener("DOMContentLoaded", () => {
  const formNgo = document.getElementById("formRegisterNgo");
  if (formNgo) {
    formNgo.addEventListener("submit", async (e) => {
      e.preventDefault();
      const dietCheckboxes = document.querySelectorAll('input[name="ngoDiet"]:checked');
      const diets = Array.from(dietCheckboxes).map(cb => cb.value);

      const payload = {
        name: document.getElementById("ngoName").value,
        ngo_type: document.getElementById("ngoType").value,
        contact_name: document.getElementById("ngoContact").value,
        phone: document.getElementById("ngoPhone").value,
        email: document.getElementById("ngoEmail").value,
        address: document.getElementById("ngoAddress").value,
        daily_capacity: parseInt(document.getElementById("ngoCapacity").value),
        current_occupancy: parseInt(document.getElementById("ngoOccupancy").value),
        latitude: parseFloat(document.getElementById("ngoLat").value),
        longitude: parseFloat(document.getElementById("ngoLon").value),
        dietary_preferences: diets.length ? diets : ["Any"],
        food_requirements: ["Cooked Meals", "Raw Produce", "Bakery"]
      };

      try {
        const res = await fetch("/api/ngos", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.status === "success") {
          showToastNotification("whatsapp", "🟢 WhatsApp Dispatched to NGO", `Kitchen '${payload.name}' activated. Alert channel open on ${payload.phone}`);
          alert("NGO registered successfully!");
          closeModal("modalNgo");
          formNgo.reset();
          loadNgos();
          loadDashboardMetrics();
          loadNotificationsFeed(false);
        } else {
          alert("Error: " + result.error);
        }
      } catch (err) {
        alert("Request failed: " + err.message);
      }
    });
  }
});

// -------------------------------------------------------------
// 4. FOOD DONATION MANAGEMENT
// -------------------------------------------------------------
async function loadDonations(statusFilter = "ALL") {
  try {
    let url = "/api/donations";
    if (statusFilter && statusFilter !== "ALL") {
      url += `?status=${encodeURIComponent(statusFilter)}`;
    }

    const res = await fetch(url);
    const data = await res.json();
    if (data.status !== "success") return;

    window.FoodLink.donations = data.donations;
    const tbody = document.getElementById("donationsTableBody");
    if (!tbody) return;

    if (data.donations.length === 0) {
      tbody.innerHTML = `<tr><td colspan="12" style="text-align:center; padding: 20px;">No donations found for this filter.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.donations.map(d => {
      const isSafe = d.safety_status === "Valid";
      const safetyBadge = isSafe
        ? `<span class="badge badge-success">✓ Valid</span>`
        : `<span class="badge badge-danger" title="${escapeHtml(d.safety_reason || 'Unsafe')}">✗ Rejected</span>`;

      let statusBadgeClass = "badge-neutral";
      if (d.status === "Available") statusBadgeClass = "badge-success";
      if (d.status === "Proposed") statusBadgeClass = "badge-warning";
      if (d.status === "Accepted") statusBadgeClass = "badge-info";
      if (d.status === "Rejected") statusBadgeClass = "badge-danger";

      const prepFormatted = formatShortDate(d.prep_time);
      const deadFormatted = formatShortDate(d.collection_deadline);

      const canMatch = isSafe && (d.status === "Available" || (d.status === "Proposed" && d.unallocated_quantity > 0));
      const matchBtn = canMatch
        ? `<button class="btn btn-primary btn-sm" onclick="matchSpecificDonation(${d.id})">🎯 Match</button>`
        : `<button class="btn btn-secondary btn-sm" disabled style="opacity:0.6;">Closed</button>`;

      return `
        <tr>
          <td>#DN-${d.id}</td>
          <td><strong>${escapeHtml(d.food_name)}</strong></td>
          <td>${escapeHtml(d.donor_name)}</td>
          <td><span class="badge badge-neutral">${escapeHtml(d.food_category)}</span></td>
          <td><strong>${d.quantity}</strong></td>
          <td><span class="badge ${d.unallocated_quantity > 0 ? 'badge-success' : 'badge-neutral'}">${d.unallocated_quantity} left</span></td>
          <td>${escapeHtml(d.storage_condition)}</td>
          <td>${prepFormatted}</td>
          <td><strong>${deadFormatted}</strong></td>
          <td>${safetyBadge}</td>
          <td><span class="badge ${statusBadgeClass}">${d.status}</span></td>
          <td>${matchBtn}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error loading donations:", err);
  }
}

function filterDonations(status, btnElem) {
  document.querySelectorAll(".active-filter").forEach(b => b.classList.remove("active-filter"));
  if (btnElem) btnElem.classList.add("active-filter");
  loadDonations(status);
}

function formatShortDate(raw) {
  if (!raw) return "-";
  try {
    const d = new Date(raw);
    return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  } catch (e) {
    return raw;
  }
}

function matchSpecificDonation(donationId) {
  navigateTo("matching");
  const sel = document.getElementById("matchDonationSelect");
  if (sel) {
    sel.value = donationId;
    executeMatchingForSelectedDonation();
  }
}

// Donation submission form handler
document.addEventListener("DOMContentLoaded", () => {
  const formDon = document.getElementById("formRegisterDonation");
  if (formDon) {
    formDon.addEventListener("submit", async (e) => {
      e.preventDefault();
      const allergenCheckboxes = document.querySelectorAll('input[name="donAllergen"]:checked');
      const allergens = Array.from(allergenCheckboxes).map(cb => cb.value);

      const payload = {
        donor_id: parseInt(document.getElementById("donDonorId").value),
        food_name: document.getElementById("donFoodName").value,
        food_category: document.getElementById("donCategory").value,
        quantity: parseInt(document.getElementById("donQuantity").value),
        prep_time: document.getElementById("donPrepTime").value,
        collection_deadline: document.getElementById("donDeadline").value,
        storage_condition: document.getElementById("donStorage").value,
        dietary_classification: document.getElementById("donDietary").value,
        allergens: allergens,
        notes: document.getElementById("donNotes").value
      };

      try {
        const res = await fetch("/api/donations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        
        if (result.status === "success") {
          const evalResult = result.safety_evaluation;
          if (evalResult.is_safe) {
            showToastNotification("sms", "📱 SMS Dispatched to Donor", `Donation '${payload.food_name}' passed safety validation. Available for matching.`);
            alert("✓ Donation passed food safety screening and is now AVAILABLE for matching!");
          } else {
            showToastNotification("sms", "⚠️ SMS Alert to Donor", `Donation '${payload.food_name}' failed food safety screening.`);
            alert("⚠️ WARNING: Donation failed safety screening!\nReasons: " + evalResult.reasons.join("\n"));
          }
          closeModal("modalDonation");
          formDon.reset();
          loadDonations();
          loadDashboardMetrics();
          loadNotificationsFeed(false);
        } else {
          alert("Error: " + result.error);
        }
      } catch (err) {
        alert("Request failed: " + err.message);
      }
    });
  }
});

// -------------------------------------------------------------
// 5. AI SMART MATCHING ENGINE
// -------------------------------------------------------------
function initMatchingView() {
  const sel = document.getElementById("matchDonationSelect");
  if (!sel) return;

  // Filter available or partially allocated donations
  const candidates = window.FoodLink.donations.filter(d => 
    d.safety_status === "Valid" && (d.status === "Available" || d.status === "Proposed")
  );

  sel.innerHTML = `<option value="">-- Choose active donation to match --</option>` +
    candidates.map(d => `<option value="${d.id}">#DN-${d.id}: ${escapeHtml(d.food_name)} (${d.unallocated_quantity} meals available)</option>`).join("");

  const btnExec = document.getElementById("btnExecuteMatch");
  if (btnExec && !btnExec.dataset.bound) {
    btnExec.addEventListener("click", executeMatchingForSelectedDonation);
    btnExec.dataset.bound = "true";
  }
}

async function executeMatchingForSelectedDonation() {
  const sel = document.getElementById("matchDonationSelect");
  const donationId = sel ? sel.value : null;

  if (!donationId) {
    alert("Please select a donation to match.");
    return;
  }

  const container = document.getElementById("matchingResultsContainer");
  container.innerHTML = `<div style="text-align:center; padding: 40px;">Evaluating multi-factor compatibility algorithms across Tricity NGOs...</div>`;

  try {
    const res = await fetch(`/api/match/${donationId}`, { method: "POST" });
    const data = await res.json();

    if (data.status !== "success") {
      container.innerHTML = `<div class="alert-banner danger"><div class="alert-content">${escapeHtml(data.error)}</div></div>`;
      return;
    }

    // Update Context Box
    const ctxBox = document.getElementById("matchingDonationContext");
    ctxBox.style.display = "block";
    document.getElementById("matchDonFoodName").textContent = data.food_name;
    document.getElementById("matchDonDetails").textContent = `Available Surplus: ${data.surplus_meals} meals`;

    // Render Gemini Explanation
    const aiBox = document.getElementById("matchingAiBox");
    const aiSummary = document.getElementById("matchingAiSummary");
    if (data.ai_explanation) {
      aiBox.style.display = "block";
      aiSummary.innerHTML = `
        <div style="margin-bottom: 8px;">${escapeHtml(data.ai_explanation.summary)}</div>
        ${data.ai_explanation.insights ? `
          <ul style="padding-left: 18px; margin-top: 6px;">
            ${data.ai_explanation.insights.map(i => `<li>${escapeHtml(i)}</li>`).join("")}
          </ul>
        ` : ''}
      `;
    }

    // Render Ranked Matches
    const matches = data.ranked_matches;
    if (!matches || matches.length === 0) {
      container.innerHTML = `<div style="text-align:center; padding: 30px;">No candidate NGOs registered.</div>`;
      return;
    }

    container.innerHTML = matches.map((m, idx) => {
      const isEligible = m.eligible;
      const rankNum = idx + 1;

      if (!isEligible) {
        return `
          <div class="match-card" style="opacity: 0.6; background: #fff5f5; border-color: #fecaca;">
            <div class="match-score-badge" style="background: #94a3b8;">
              <span class="score-val">0</span>
              <span class="score-label">Ineligible</span>
            </div>
            <div class="match-details">
              <h4 style="font-size: 16px; color: #991b1b;">${escapeHtml(m.ngo_name)}</h4>
              <p style="font-size: 13px; color: #b91c1c; margin-top: 4px;">
                <strong>Reason:</strong> ${m.rejection_reasons.join("; ")}
              </p>
            </div>
          </div>
        `;
      }

      const factors = m.factors || {};

      return `
        <div class="match-card">
          <div class="match-score-badge">
            <span class="score-val">${m.matching_score}</span>
            <span class="score-label">Rank #${rankNum}</span>
          </div>

          <div class="match-details">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:10px;">
              <div>
                <h4 style="font-size: 16px; font-weight: 700; color: var(--navy-900);">${escapeHtml(m.ngo_name)}</h4>
                <div style="font-size: 12.5px; color: var(--navy-500); margin-top: 2px;">
                  📍 ${escapeHtml(m.address)} • <strong>${m.distance_km} km away</strong> • Capacity: ${m.available_capacity} meals available
                </div>
              </div>

              <button class="btn btn-primary" onclick="openAllocationModal(${data.donation_id}, ${m.ngo_id}, ${m.proposed_meals}, '${escapeHtml(m.ngo_name)}', ${m.matching_score}, ${m.distance_km}, ${data.surplus_meals})">
                🤝 Propose Allocation (${m.proposed_meals} Meals)
              </button>
            </div>

            <!-- Factor breakdown bars -->
            <div class="match-factors">
              <div class="factor-item">
                <span>Distance (30%): <strong>${factors.distance_score || 0}</strong></span>
                <div class="factor-bar"><div class="factor-fill" style="width: ${factors.distance_score || 0}%;"></div></div>
              </div>
              <div class="factor-item">
                <span>Quantity Fit (25%): <strong>${factors.quantity_score || 0}</strong></span>
                <div class="factor-bar"><div class="factor-fill" style="width: ${factors.quantity_score || 0}%;"></div></div>
              </div>
              <div class="factor-item">
                <span>Urgency (20%): <strong>${factors.urgency_score || 0}</strong></span>
                <div class="factor-bar"><div class="factor-fill" style="width: ${factors.urgency_score || 0}%;"></div></div>
              </div>
              <div class="factor-item">
                <span>Dietary Match (15%): <strong>${factors.preference_score || 0}</strong></span>
                <div class="factor-bar"><div class="factor-fill" style="width: ${factors.preference_score || 0}%;"></div></div>
              </div>
              <div class="factor-item">
                <span>Capacity Room (10%): <strong>${factors.capacity_score || 0}</strong></span>
                <div class="factor-bar"><div class="factor-fill" style="width: ${factors.capacity_score || 0}%;"></div></div>
              </div>
            </div>

            <div style="font-size: 12.5px; color: var(--navy-700); line-height: 1.4;">
              💡 <em>${escapeHtml(m.explanation)}</em>
            </div>
          </div>
        </div>
      `;
    }).join("");

  } catch (err) {
    container.innerHTML = `<div style="color:red; padding:20px;">Matching call failed: ${err.message}</div>`;
  }
}

function openAllocationModal(donId, ngoId, proposedMeals, ngoName, score, dist, maxSurplus) {
  document.getElementById("allocDonationId").value = donId;
  document.getElementById("allocNgoId").value = ngoId;
  document.getElementById("allocDistance").value = dist;
  document.getElementById("allocScore").value = score;

  document.getElementById("allocTargetNgoName").textContent = ngoName;
  document.getElementById("allocTargetDetails").textContent = `Matching Score: ${score}/100 • Distance: ${dist} km`;
  document.getElementById("allocMealsCount").value = proposedMeals;
  document.getElementById("allocMealsCount").max = maxSurplus;
  document.getElementById("allocMaxAllowedText").textContent = `Max available unallocated surplus: ${maxSurplus} meals`;

  openModal("modalAllocate");
}

// Allocation transaction form submission
document.addEventListener("DOMContentLoaded", () => {
  const formAlloc = document.getElementById("formConfirmAllocation");
  if (formAlloc) {
    formAlloc.addEventListener("submit", async (e) => {
      e.preventDefault();
      const payload = {
        donation_id: parseInt(document.getElementById("allocDonationId").value),
        ngo_id: parseInt(document.getElementById("allocNgoId").value),
        allocated_meals: parseInt(document.getElementById("allocMealsCount").value),
        distance_km: parseFloat(document.getElementById("allocDistance").value),
        matching_score: parseFloat(document.getElementById("allocScore").value),
        notes: document.getElementById("allocNotes").value
      };

      try {
        const res = await fetch("/api/allocations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.status === "success") {
          showToastNotification("whatsapp", "🟢 WhatsApp Match Dispatched to NGO", `Allocation of ${payload.allocated_meals} meals sent to recipient kitchen.`);
          alert("✓ Allocation transaction committed successfully! Status is PROPOSED until accepted.");
          closeModal("modalAllocate");
          loadDashboardMetrics();
          loadDonations();
          executeMatchingForSelectedDonation();
          loadNotificationsFeed(false);
        } else {
          alert("Transaction Failed: " + result.error);
        }
      } catch (err) {
        alert("Request failed: " + err.message);
      }
    });
  }
});

// -------------------------------------------------------------
// 6. DEMAND FORECASTING
// -------------------------------------------------------------
function initForecastingView() {
  const sel = document.getElementById("forecastNgoSelect");
  if (!sel) return;

  sel.innerHTML = `<option value="">-- Choose recipient organization --</option>` +
    window.FoodLink.ngos.map(n => `<option value="${n.id}">${escapeHtml(n.name)} (${n.daily_capacity} meals/day)</option>`).join("");

  const btn = document.getElementById("btnLoadForecast");
  if (btn && !btn.dataset.bound) {
    btn.addEventListener("click", loadForecastForSelectedNgo);
    btn.dataset.bound = "true";
  }
}

async function loadForecastForSelectedNgo() {
  const sel = document.getElementById("forecastNgoSelect");
  const ngoId = sel ? sel.value : null;

  if (!ngoId) {
    alert("Please select an NGO to forecast.");
    return;
  }

  try {
    const res = await fetch(`/api/forecast/${ngoId}`);
    const data = await res.json();
    if (data.status !== "success") return;

    const fc = data.forecast;
    document.getElementById("forecastKpiGrid").style.display = "grid";
    document.getElementById("fcPredictedMeals").textContent = fc.predicted_meals;
    document.getElementById("fcHistoricalAvg").textContent = `${fc.historical_avg} meals`;
    document.getElementById("fcRecentAvg").textContent = `${fc.recent_avg} meals`;
    document.getElementById("fcTrendLabel").textContent = fc.trend;
    document.getElementById("fcTrendPct").textContent = `${fc.trend_percentage > 0 ? '+' : ''}${fc.trend_percentage}% vs history`;

    // AI Commentary
    const aiBox = document.getElementById("forecastAiBox");
    aiBox.style.display = "block";
    document.getElementById("forecastAiSummary").innerHTML = `
      <p><strong>Baseline Forecast Analysis:</strong> ${escapeHtml(data.ai_summary.summary)}</p>
      ${data.ai_summary.action_recommendation ? `<p style="margin-top:6px; color:#1e40af;"><strong>Action:</strong> ${escapeHtml(data.ai_summary.action_recommendation)}</p>` : ''}
    `;

    // Forecast Chart
    document.getElementById("forecastChartCard").style.display = "block";
    renderForecastChart(fc.history_series, fc.forecast_series);
  } catch (err) {
    console.error("Forecast error:", err);
  }
}

function renderForecastChart(historySeries, forecastSeries) {
  const ctx = document.getElementById("forecastChart");
  if (!ctx) return;

  if (window.FoodLink.charts.forecast) {
    window.FoodLink.charts.forecast.destroy();
  }

  const histLabels = (historySeries || []).map(h => h.date ? h.date.slice(5) : "");
  const histData = (historySeries || []).map(h => h.meals_demanded);

  const foreLabels = (forecastSeries || []).map(f => `${f.day} (${f.date.slice(5)})`);
  const foreData = (forecastSeries || []).map(f => f.predicted_meals);

  const allLabels = [...histLabels, ...foreLabels];
  const historyPlot = [...histData, ...Array(foreData.length).fill(null)];
  const forecastPlot = [...Array(histData.length - 1).fill(null), histData[histData.length - 1], ...foreData];

  window.FoodLink.charts.forecast = new Chart(ctx, {
    type: "line",
    data: {
      labels: allLabels,
      datasets: [
        {
          label: "Historical Demand",
          data: historyPlot,
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59, 130, 246, 0.08)",
          fill: true,
          tension: 0.2
        },
        {
          label: "Projected Demand (Statistical Formula)",
          data: forecastPlot,
          borderColor: "#10b981",
          borderDash: [5, 5],
          backgroundColor: "rgba(16, 185, 129, 0.12)",
          fill: true,
          tension: 0.2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top" }
      },
      scales: {
        y: { beginAtZero: false }
      }
    }
  });
}

// -------------------------------------------------------------
// 7. FOOD SAFETY INSPECTOR & SIMULATOR
// -------------------------------------------------------------
function loadFoodSafetyAudit() {
  const tbody = document.getElementById("safetyAuditTableBody");
  if (!tbody) return;

  const donations = window.FoodLink.donations;
  if (!donations || donations.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px;">No donations recorded for inspection.</td></tr>`;
    return;
  }

  tbody.innerHTML = donations.map(d => {
    const isSafe = d.safety_status === "Valid";
    const statusBadge = isSafe
      ? `<span class="badge badge-success">✓ Passed Risk Screening</span>`
      : `<span class="badge badge-danger">✗ Rejected</span>`;

    const allergens = Array.isArray(d.allergens) && d.allergens.length > 0
      ? d.allergens.join(", ")
      : "None Declared";

    return `
      <tr>
        <td>#DN-${d.id}</td>
        <td><strong>${escapeHtml(d.food_name)}</strong></td>
        <td>${escapeHtml(d.food_category)}</td>
        <td>${escapeHtml(d.storage_condition)}</td>
        <td>${formatShortDate(d.prep_time)}</td>
        <td>${formatShortDate(d.collection_deadline)}</td>
        <td>${escapeHtml(allergens)}</td>
        <td>${statusBadge}</td>
        <td><small style="color: ${isSafe ? '#166534' : '#b91c1c'};">${escapeHtml(d.safety_reason || 'Complies with category temperature and shelf-life thresholds.')}</small></td>
      </tr>
    `;
  }).join("");

  // Bind Simulator button
  const btnSim = document.getElementById("btnTestSafetySim");
  if (btnSim && !btnSim.dataset.bound) {
    btnSim.addEventListener("click", runFoodSafetySimulator);
    btnSim.dataset.bound = "true";
  }
}

function runFoodSafetySimulator() {
  const category = document.getElementById("simCategory").value;
  const storage = document.getElementById("simStorage").value;
  const elapsed = parseFloat(document.getElementById("simElapsedHours").value);
  const windowHrs = parseFloat(document.getElementById("simWindowHours").value);

  const resBox = document.getElementById("simSafetyResultBox");
  resBox.style.display = "block";

  // Comprehensive category rule check
  let isSafe = true;
  let reasons = [];

  const maxWindows = {
    "Cooked Meals": { "Hot-hold (>60°C)": 6.0, "Chilled (0-4°C)": 24.0, "Room Temp (20-25°C)": 4.0, "Frozen (<-18°C)": 72.0, "_default": 4.0 },
    "Perishable Dairy": { "Chilled (0-4°C)": 12.0, "Frozen (<-18°C)": 48.0, "_default": 2.0 },
    "Bakery": { "Room Temp (20-25°C)": 36.0, "Chilled (0-4°C)": 48.0, "_default": 36.0 },
    "Raw Produce": { "Room Temp (20-25°C)": 48.0, "Chilled (0-4°C)": 96.0, "_default": 48.0 },
    "Packaged": { "Room Temp (20-25°C)": 72.0, "Chilled (0-4°C)": 72.0, "_default": 72.0 }
  };

  const catRules = maxWindows[category] || { "_default": 4.0 };
  const maxLimit = catRules[storage] || catRules["_default"] || 4.0;

  if (category === "Cooked Meals" && storage === "Room Temp (20-25°C)" && elapsed > 4.0) {
    isSafe = false;
    reasons.push("Cooked food left at room temperature (Danger Zone 20-25°C) exceeds the strict 4-hour microbial threshold.");
  }

  if (category === "Perishable Dairy" && (storage === "Room Temp (20-25°C)" || storage === "Hot-hold (>60°C)")) {
    isSafe = false;
    reasons.push("Dairy items (paneer, curd, milk desserts) require active refrigeration (0-4°C) or freezing.");
  }

  if (windowHrs > maxLimit) {
    isSafe = false;
    reasons.push(`Requested transit window (${windowHrs} hrs) exceeds the maximum safe limit (${maxLimit} hrs) for ${category} under '${storage}'.`);
  }

  if ((elapsed + windowHrs) > (maxLimit * 1.5)) {
    isSafe = false;
    reasons.push(`Combined elapsed age + transit (${elapsed + windowHrs} hrs) exceeds total safe shelf life.`);
  }

  if (isSafe) {
    resBox.style.background = "#f0fdf4";
    resBox.style.border = "1px solid #bbf7d0";
    resBox.innerHTML = `
      <h4 style="color: #15803d; font-size: 15px; font-weight:700;">✓ Pass — Safe Collection Window Approved</h4>
      <p style="font-size: 13px; color: #166534; margin-top: 4px;">
        ${category} under '${storage}' conforms to safe redistribution guidelines for requested ${windowHrs}-hour transit window.
      </p>
    `;
  } else {
    resBox.style.background = "#fef2f2";
    resBox.style.border = "1px solid #fecaca";
    resBox.innerHTML = `
      <h4 style="color: #b91c1c; font-size: 15px; font-weight:700;">✗ Flagged Unsafe — Risk Screening Rejection</h4>
      <p style="font-size: 13px; color: #991b1b; margin-top: 4px;">
        ${reasons.join("<br>")}
      </p>
    `;
  }
}

// Utility HTML escape
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// -------------------------------------------------------------
// 8. REAL-TIME NOTIFICATION DISPATCH ENGINE
// -------------------------------------------------------------
let currentNotificationFilter = "ALL";
let cachedNotifications = [];

function showToastNotification(channel, title, message) {
  const container = document.getElementById("toastContainer");
  if (!container) return;

  const toast = document.createElement("div");
  const channelClass = (channel || "sms").toLowerCase();
  toast.className = `toast-item ${channelClass}`;

  let icon = "📱";
  let label = "SMS Message";
  if (channelClass.includes("whatsapp")) {
    icon = "🟢";
    label = "WhatsApp Dispatch";
  } else if (channelClass.includes("dispatch")) {
    icon = "🚗";
    label = "Volunteer Road Route";
  }

  toast.innerHTML = `
    <div class="toast-header">
      <div style="display:flex; align-items:center; gap:6px;">
        <span>${icon}</span>
        <strong style="font-size:12.5px; color:var(--navy-900);">${escapeHtml(title)}</strong>
      </div>
      <span class="badge ${channelClass.includes('whatsapp') ? 'badge-success' : (channelClass.includes('dispatch') ? 'badge-warning' : 'badge-info')}" style="font-size:10px;">${label}</span>
    </div>
    <div class="toast-body" style="font-size:12.5px; margin-top:4px;">
      ${escapeHtml(message)}
    </div>
  `;

  container.appendChild(toast);

  // Auto remove after 5 seconds
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(50px)";
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

async function loadNotificationsFeed(renderToView = true, filterType = "ALL") {
  if (filterType) currentNotificationFilter = filterType;
  try {
    const res = await fetch("/api/notifications?limit=60");
    const data = await res.json();
    if (data.status !== "success") return;

    cachedNotifications = data.notifications || [];

    // Update Header Badge Count
    const badge = document.getElementById("notifBadgeCount");
    if (badge) badge.textContent = cachedNotifications.length;

    // Update Stakeholder Counts
    const cAll = cachedNotifications.length;
    const cDonor = cachedNotifications.filter(n => n.recipient_type === "Donor").length;
    const cNgo = cachedNotifications.filter(n => n.recipient_type === "NGO").length;
    const cVol = cachedNotifications.filter(n => n.recipient_type === "Delivery Volunteer").length;

    const elAll = document.getElementById("notifCountAll");
    if (elAll) elAll.textContent = cAll;
    const elDon = document.getElementById("notifCountDonor");
    if (elDon) elDon.textContent = cDonor;
    const elNgo = document.getElementById("notifCountNgo");
    if (elNgo) elNgo.textContent = cNgo;
    const elVol = document.getElementById("notifCountVolunteer");
    if (elVol) elVol.textContent = cVol;

    if (renderToView) {
      renderNotificationCards(cachedNotifications, currentNotificationFilter);
    }
  } catch (err) {
    console.error("Notifications fetch error:", err);
  }
}

function filterNotifications(filterType, btnElem) {
  currentNotificationFilter = filterType;
  if (btnElem && btnElem.parentElement) {
    btnElem.parentElement.querySelectorAll("button").forEach(b => {
      b.className = "btn btn-sm btn-secondary";
    });
    btnElem.className = "btn btn-sm btn-primary active-filter";
  }
  renderNotificationCards(cachedNotifications, currentNotificationFilter);
}

function renderNotificationCards(items, filterType) {
  const container = document.getElementById("notificationsFeedContainer");
  if (!container) return;

  let filtered = items;
  if (filterType !== "ALL") {
    filtered = items.filter(n => n.recipient_type === filterType);
  }

  if (filtered.length === 0) {
    container.innerHTML = `<div style="text-align:center; padding:40px; color:var(--navy-500); background:#f8fafc; border-radius:var(--radius-md);">No notification dispatches found for this filter. Perform an action (register, donate, match, or route) to see live automated dispatches.</div>`;
    return;
  }

  container.innerHTML = filtered.map(n => {
    const isWhatsApp = n.channel === "WhatsApp";
    const isDispatch = n.channel === "Dispatch Packet";
    const channelClass = isWhatsApp ? "channel-whatsapp" : (isDispatch ? "channel-dispatch" : "channel-sms");
    const iconClass = isWhatsApp ? "notif-icon-whatsapp" : (isDispatch ? "notif-icon-dispatch" : "notif-icon-sms");
    const iconSymbol = isWhatsApp ? "🟢" : (isDispatch ? "🚗" : "💬");

    const channelBadge = isWhatsApp
      ? `<span class="badge badge-success" style="font-size:11px;">WhatsApp Gateway</span>`
      : (isDispatch
          ? `<span class="badge badge-warning" style="font-size:11px;">Volunteer Route Packet</span>`
          : `<span class="badge badge-info" style="font-size:11px;">SMS Gateway</span>`);

    const timeStr = n.created_at ? n.created_at.slice(11, 16) : "--:--";

    return `
      <div class="notif-card ${channelClass}">
        <div class="notif-icon-bubble ${iconClass}">
          ${iconSymbol}
        </div>
        <div class="notif-content-wrap">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:6px;">
            <div>
              <span style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--navy-500); letter-spacing:0.5px;">To: ${escapeHtml(n.recipient_type)} • ${escapeHtml(n.recipient_name)}</span>
              <h4 style="font-size:14.5px; font-weight:700; color:var(--navy-900); margin-top:2px;">${escapeHtml(n.title)}</h4>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
              ${channelBadge}
              <span class="badge badge-success" style="font-size:10px;">✓ ${escapeHtml(n.status)}</span>
              <span style="font-size:11.5px; color:var(--navy-500); font-weight:600;">${timeStr}</span>
            </div>
          </div>
          <div style="font-size:12px; color:var(--navy-600); margin-top:4px;">
            Contact Channel: <code>${escapeHtml(n.contact_info)}</code>
          </div>
          <div class="notif-bubble-msg">
            ${escapeHtml(n.message)}
          </div>
        </div>
      </div>
    `;
  }).join("");
}

// Bind Simulator test buttons in Live Alerts view
document.addEventListener("DOMContentLoaded", () => {
  const btnSimNgo = document.getElementById("btnSimulateNgoAlert");
  if (btnSimNgo) {
    btnSimNgo.addEventListener("click", async () => {
      try {
        const payload = {
          recipient_type: "NGO",
          recipient_name: "Govinda Seva Sadan",
          channel: "WhatsApp",
          contact_info: "+91 62016 23632",
          title: "Surplus Food Alert: 100 Meals from CGCU",
          message: "🟢 Urgent Surplus Alert: CGCU Jhanjeri has 100 hot cooked meals available (Rajma & Rice). Safe collection window: 2.5 hours remaining. Reply 1 to Accept."
        };
        const res = await fetch("/api/notifications", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        showToastNotification("whatsapp", "🟢 WhatsApp Dispatched to NGO", "Surplus food match alert sent to Govinda Seva Sadan (+91 62016 23632).");
        loadNotificationsFeed(true, currentNotificationFilter);
      } catch (err) {
        alert("Alert dispatch error: " + err.message);
      }
    });
  }

  const btnSimDriver = document.getElementById("btnSimulateDriverAlert");
  if (btnSimDriver) {
    btnSimDriver.addEventListener("click", async () => {
      try {
        const payload = {
          recipient_type: "Delivery Volunteer",
          recipient_name: "Volunteer Govind Kumar",
          channel: "Dispatch Packet",
          contact_info: "+91 62016 23632 (Mobile GPS)",
          title: "Delivery Task Assigned: CGCU -> Govinda Seva Sadan",
          message: "🚗 Pickup Assigned: Collect 100 meals from CGCU Canteen (Jhanjeri) -> Deliver to Govinda Seva Sadan. Road Distance: 6.87 km (6.8 min drive). Turn-by-turn route link: foodlink.ai/route/7"
        };
        const res = await fetch("/api/notifications", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        showToastNotification("dispatch", "🚗 Delivery Dispatch Sent", "Turn-by-turn road route sent to Volunteer Govind Kumar.");
        loadNotificationsFeed(true, currentNotificationFilter);
      } catch (err) {
        alert("Alert dispatch error: " + err.message);
      }
    });
  }

  const btnRefNotifs = document.getElementById("btnRefreshNotifs");
  if (btnRefNotifs) {
    btnRefNotifs.addEventListener("click", () => {
      loadNotificationsFeed(true, currentNotificationFilter);
      showToastNotification("sms", "🔄 Telemetry Refreshed", "Latest communication dispatches synced.");
    });
  }
});

