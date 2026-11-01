/**
 * FoodLink AI - Leaflet Map & OSRM Route Optimization Controller
 * Renders OpenStreetMap tiles, custom delivery markers, GeoJSON driving polylines & stop sequences
 */

function initRoutingView() {
  initLeafletMap();
  populateRouteSelectors();

  const btnCalc = document.getElementById("btnCalculateRoute");
  if (btnCalc && !btnCalc.dataset.bound) {
    btnCalc.addEventListener("click", calculateAndRenderRoute);
    btnCalc.dataset.bound = "true";
  }

  const btnActive = document.getElementById("btnRouteFromActive");
  if (btnActive && !btnActive.dataset.bound) {
    btnActive.addEventListener("click", loadStopsFromActiveAllocations);
    btnActive.dataset.bound = "true";
  }

  const btnAll = document.getElementById("btnShowAllMarkers");
  if (btnAll && !btnAll.dataset.bound) {
    btnAll.addEventListener("click", () => {
      if (window.FoodLink.routeLayer) window.FoodLink.routeLayer.clearLayers();
      const seqBox = document.getElementById("routeStopsSequenceBox");
      if (seqBox) seqBox.style.display = "none";
      const metricsRow = document.getElementById("routeMetricsRow");
      if (metricsRow) metricsRow.style.display = "none";
      const warnBox = document.getElementById("routeWarningBox");
      if (warnBox) warnBox.style.display = "none";
      const fallbackBox = document.getElementById("routeFallbackBox");
      if (fallbackBox) fallbackBox.style.display = "none";
      plotAllLocationsOverview();
    });
    btnAll.dataset.bound = "true";
  }
}

function initLeafletMap() {
  const mapElem = document.getElementById("routeMap");
  if (!mapElem) return;

  // If already initialized, invalidate size and ensure overview is plotted if empty
  if (window.FoodLink.mapInstance) {
    setTimeout(() => {
      window.FoodLink.mapInstance.invalidateSize();
      if (window.FoodLink.markersLayer && window.FoodLink.markersLayer.getLayers().length === 0) {
        plotAllLocationsOverview();
      }
    }, 200);
    return;
  }

  // Centered on Chandigarh - Mohali Tricity Region (Sector 17 / Phase 7 area)
  const defaultCenter = [30.7333, 76.7794];
  const map = L.map("routeMap").setView(defaultCenter, 12);

  // OpenStreetMap tile layer with required attribution
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors'
  }).addTo(map);

  window.FoodLink.mapInstance = map;
  window.FoodLink.markersLayer = L.layerGroup().addTo(map);
  window.FoodLink.routeLayer = L.layerGroup().addTo(map);

  // Initial plot of all registered donors and NGOs as discovery layer
  plotAllLocationsOverview();
}

function plotAllLocationsOverview() {
  if (!window.FoodLink.markersLayer) return;
  window.FoodLink.markersLayer.clearLayers();

  const donors = window.FoodLink.donors || [];
  const ngos = window.FoodLink.ngos || [];
  const bounds = [];

  // Plot Donors with custom blue icons
  donors.forEach(d => {
    if (d.latitude && d.longitude) {
      const pos = [d.latitude, d.longitude];
      bounds.push(pos);

      const donorIcon = L.divIcon({
        html: `
          <div style="
            background: #2563eb;
            color: white;
            border: 2px solid white;
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 700;
            box-shadow: 0 3px 10px rgba(37,99,235,0.4);
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 4px;
          ">
            <span>🏢</span> ${escapeHtml(d.name.length > 18 ? d.name.slice(0, 16) + '...' : d.name)}
          </div>
        `,
        className: "custom-donor-marker",
        iconSize: [140, 26],
        iconAnchor: [70, 13]
      });

      const marker = L.marker(pos, { icon: donorIcon });
      marker.bindPopup(`
        <div style="font-family: sans-serif; font-size: 12.5px; line-height: 1.5; min-width: 200px;">
          <div style="color: #2563eb; font-weight: 700; font-size: 11px; text-transform: uppercase;">🏢 Food Donor</div>
          <strong style="font-size: 14px; color: #0f172a;">${escapeHtml(d.name)}</strong>
          <div style="color: #64748b; font-size: 12px; margin-top: 2px;">${escapeHtml(d.donor_type || 'Donor')} • ${escapeHtml(d.address)}</div>
          <div style="margin-top: 6px; font-size: 11.5px; color: #475569;">
            Contact: <strong>${escapeHtml(d.contact_name || 'N/A')}</strong> (${escapeHtml(d.phone || 'N/A')})
          </div>
          <div style="margin-top: 8px;">
            <button class="btn btn-primary btn-sm" style="width: 100%; font-size: 11px;" onclick="selectDonorForRoute(${d.id})">
              Set as Route Pickup Origin
            </button>
          </div>
        </div>
      `);
      window.FoodLink.markersLayer.addLayer(marker);
    }
  });

  // Plot NGOs with custom green icons
  ngos.forEach(n => {
    if (n.latitude && n.longitude) {
      const pos = [n.latitude, n.longitude];
      bounds.push(pos);

      const ngoIcon = L.divIcon({
        html: `
          <div style="
            background: #059669;
            color: white;
            border: 2px solid white;
            border-radius: 999px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 700;
            box-shadow: 0 3px 10px rgba(5,150,105,0.4);
            white-space: nowrap;
            display: flex;
            align-items: center;
            gap: 4px;
          ">
            <span>🤝</span> ${escapeHtml(n.name.length > 18 ? n.name.slice(0, 16) + '...' : n.name)}
          </div>
        `,
        className: "custom-ngo-marker",
        iconSize: [140, 26],
        iconAnchor: [70, 13]
      });

      const marker = L.marker(pos, { icon: ngoIcon });
      marker.bindPopup(`
        <div style="font-family: sans-serif; font-size: 12.5px; line-height: 1.5; min-width: 200px;">
          <div style="color: #059669; font-weight: 700; font-size: 11px; text-transform: uppercase;">🤝 Recipient Organization</div>
          <strong style="font-size: 14px; color: #0f172a;">${escapeHtml(n.name)}</strong>
          <div style="color: #64748b; font-size: 12px; margin-top: 2px;">${escapeHtml(n.ngo_type || 'NGO')} • ${escapeHtml(n.address)}</div>
          <div style="margin-top: 6px; font-size: 11.5px; color: #475569;">
            Capacity: <strong>${n.available_capacity || n.daily_capacity}</strong> meals headroom (${n.daily_capacity} max)
          </div>
          <div style="margin-top: 8px;">
            <button class="btn btn-secondary btn-sm" style="width: 100%; font-size: 11px;" onclick="toggleNgoStopForRoute(${n.id})">
              Toggle as Delivery Stop
            </button>
          </div>
        </div>
      `);
      window.FoodLink.markersLayer.addLayer(marker);
    }
  });

  // Fit bounds if we have points
  if (bounds.length > 0 && window.FoodLink.mapInstance) {
    window.FoodLink.mapInstance.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
  }
}

function selectDonorForRoute(donorId) {
  const sel = document.getElementById("routeDonorSelect");
  if (sel) {
    sel.value = donorId;
    alert("Selected as starting donor pickup origin. Now select recipient NGOs and click 'Optimize Delivery Route'.");
  }
}

function toggleNgoStopForRoute(ngoId) {
  const cb = document.querySelector(`input[name="routeNgoStops"][value="${ngoId}"]`);
  if (cb) {
    cb.checked = !cb.checked;
    alert(`${cb.checked ? "Added to" : "Removed from"} delivery stops.`);
  }
}

function populateRouteSelectors() {
  // Donor selector
  const donSel = document.getElementById("routeDonorSelect");
  if (donSel) {
    donSel.innerHTML = `<option value="">-- Select Donor Location --</option>` +
      (window.FoodLink.donors || []).map(d => `<option value="${d.id}">${escapeHtml(d.name)} (${escapeHtml(d.address)})</option>`).join("");
  }

  // NGO Checkboxes
  const ngoBox = document.getElementById("routeNgoCheckboxes");
  if (ngoBox) {
    if (!window.FoodLink.ngos || window.FoodLink.ngos.length === 0) {
      ngoBox.innerHTML = `<em>No NGOs available.</em>`;
      return;
    }
    ngoBox.innerHTML = window.FoodLink.ngos.map(n => `
      <label style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; cursor: pointer;">
        <input type="checkbox" name="routeNgoStops" value="${n.id}">
        <span><strong>${escapeHtml(n.name)}</strong> (${escapeHtml(n.address)})</span>
      </label>
    `).join("");
  }
}

async function loadStopsFromActiveAllocations() {
  try {
    const res = await fetch("/api/dashboard");
    const data = await res.json();
    const allocations = data.recent_allocations;

    if (!allocations || allocations.length === 0) {
      alert("No active allocations found to auto-load. Propose an allocation first in the Matching tab!");
      return;
    }

    const first = allocations[0];
    const donorMatch = (window.FoodLink.donors || []).find(d => d.name === first.donor_name);
    if (donorMatch) {
      document.getElementById("routeDonorSelect").value = donorMatch.id;
    }

    const allocatedNgoNames = allocations.map(a => a.ngo_name);
    document.querySelectorAll('input[name="routeNgoStops"]').forEach(cb => {
      const ngoObj = (window.FoodLink.ngos || []).find(n => String(n.id) === cb.value);
      if (ngoObj && allocatedNgoNames.includes(ngoObj.name)) {
        cb.checked = true;
      } else {
        cb.checked = false;
      }
    });

    calculateAndRenderRoute();
  } catch (err) {
    alert("Failed to load active allocation stops: " + err.message);
  }
}

async function calculateAndRenderRoute() {
  const donorId = document.getElementById("routeDonorSelect").value;
  const ngoCheckboxes = document.querySelectorAll('input[name="routeNgoStops"]:checked');
  const ngoIds = Array.from(ngoCheckboxes).map(cb => parseInt(cb.value));

  if (!donorId) {
    alert("Please select a starting donor location.");
    return;
  }

  if (ngoIds.length === 0) {
    alert("Please check at least one recipient NGO stop.");
    return;
  }

  const payload = {
    donor_id: parseInt(donorId),
    ngo_ids: ngoIds
  };

  try {
    const res = await fetch("/api/route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await res.json();

    if (result.status !== "success") {
      alert("Route calculation error: " + (result.error || "Unknown"));
      return;
    }

    // Update Route KPI Metrics
    const metricsRow = document.getElementById("routeMetricsRow");
    if (metricsRow) metricsRow.style.display = "grid";
    document.getElementById("routeTotalDistance").textContent = `${result.total_distance_km} km`;
    document.getElementById("routeTotalDuration").textContent = `${result.total_duration_minutes} min`;
    document.getElementById("routeStopsCount").textContent = result.stops_count;
    document.getElementById("routeEngineMode").textContent = result.is_osrm ? "OSRM Road Routing" : "Haversine Fallback";

    const completionElem = document.getElementById("routeCompletionEta");
    if (completionElem) {
      completionElem.textContent = result.estimated_completion_display || (result.estimated_completion ? result.estimated_completion.slice(11) : "--:--");
    }

    const algoElem = document.getElementById("routeAlgorithmLabel");
    if (algoElem && result.algorithm) {
      algoElem.textContent = result.algorithm;
    }

    // Engine fallback notices
    const fallbackBox = document.getElementById("routeFallbackBox");
    const fallbackText = document.getElementById("routeFallbackText");
    if (fallbackBox && fallbackText) {
      if (!result.is_osrm || (result.fallback_notices && result.fallback_notices.length > 0)) {
        fallbackBox.style.display = "flex";
        fallbackText.innerHTML = `<strong>Routing Notice:</strong> ${escapeHtml(result.routing_mode)}. ` +
          (result.fallback_notices ? result.fallback_notices.join("<br>") : "");
      } else {
        fallbackBox.style.display = "none";
      }
    }

    // Deadline Warnings
    const warnBox = document.getElementById("routeWarningBox");
    if (result.deadline_warnings && result.deadline_warnings.length > 0) {
      warnBox.style.display = "flex";
      document.getElementById("routeWarningText").innerHTML = result.deadline_warnings.join("<br>");
    } else {
      warnBox.style.display = "none";
    }

    // Render Stop Sequence Timeline with per-leg ETAs
    renderRouteTimeline(result.ordered_stops, result.legs, result.estimated_completion_display);

    // Render GeoJSON Route on Leaflet Map
    renderGeoJsonOnMap(result);

    // Live Notification Toast & Feed Sync
    if (typeof showToastNotification === "function") {
      showToastNotification("dispatch", "🚗 Volunteer Route Dispatched", `Turn-by-turn road route generated: ${result.total_distance_km} km (~${result.total_duration_minutes} min drive).`);
    }
    if (typeof loadNotificationsFeed === "function") {
      loadNotificationsFeed(false);
    }

  } catch (err) {
    alert("Routing request failed: " + err.message);
  }
}

function renderRouteTimeline(orderedStops, legs, finalEta) {
  const box = document.getElementById("routeStopsSequenceBox");
  const timeline = document.getElementById("routeStopsTimeline");
  box.style.display = "block";

  timeline.innerHTML = orderedStops.map((s, idx) => {
    const isDonor = (idx === 0);
    const badgeType = isDonor ? "badge-info" : "badge-success";
    const titlePrefix = isDonor ? "Pickup Origin" : `Delivery Stop #${idx}`;

    const legInfo = (!isDonor && legs && legs[idx - 1])
      ? `<div style="font-size: 12px; color: #0284c7; margin-top: 6px; display: flex; align-items: center; gap: 8px;">
           <span>↳ Leg #${idx}: <strong>${legs[idx-1].distance_km} km</strong> • ~<strong>${legs[idx-1].duration_min} min drive</strong> from ${escapeHtml(legs[idx-1].from_stop)}</span>
         </div>`
      : "";

    const etaDisplay = s.eta_display || (s.eta ? s.eta.slice(11) : "--:--");
    const deadlineAlert = s.deadline_status === "overdue"
      ? `<span class="badge badge-danger" style="font-size: 11px;">⚠️ Overdue</span>`
      : (s.deadline_status === "tight"
          ? `<span class="badge badge-warning" style="font-size: 11px;">⏱️ Tight Margin</span>`
          : `<span class="badge badge-success" style="font-size: 11px;">✓ On Schedule</span>`);

    return `
      <div style="background: white; border: 1px solid var(--border-light); border-left: 4px solid ${isDonor ? '#3b82f6' : '#10b981'}; border-radius: var(--radius-md); padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
          <div>
            <span class="badge ${badgeType}">${titlePrefix}</span>
            <strong style="margin-left: 8px; font-size: 14.5px; color: var(--navy-900);">${escapeHtml(s.name)}</strong>
            <div style="font-size: 12px; color: var(--navy-500); margin-top: 2px;">📍 ${escapeHtml(s.address)}</div>
          </div>
          <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 2px;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <span style="font-size: 14px; font-weight: 700; color: var(--navy-900);">ETA: ${etaDisplay}</span>
              ${!isDonor ? deadlineAlert : ''}
            </div>
            <div style="font-size: 11.5px; color: var(--navy-500);">Cumulative: ${s.cumulative_distance_km} km (${s.cumulative_travel_minutes} min total)</div>
          </div>
        </div>
        ${legInfo}
      </div>
    `;
  }).join("");
}

function renderGeoJsonOnMap(routeResult) {
  const map = window.FoodLink.mapInstance;
  if (!map) return;

  // Clear previous layers
  window.FoodLink.routeLayer.clearLayers();
  window.FoodLink.markersLayer.clearLayers();

  const stops = routeResult.ordered_stops;
  const latLngs = [];

  // Plot custom numbered markers for each stop with ETA badges
  stops.forEach((s, idx) => {
    const isDonor = (idx === 0);
    const pos = [s.latitude, s.longitude];
    latLngs.push(pos);

    const color = isDonor ? "#2563eb" : "#059669";
    const label = isDonor ? "ORIGIN (Pickup)" : `STOP #${idx} (${s.eta_display || (s.eta ? s.eta.slice(11) : '')})`;

    const iconHtml = `
      <div style="
        background: ${color};
        color: white;
        border: 2px solid white;
        border-radius: 999px;
        padding: 4px 10px;
        font-size: 11px;
        font-weight: 700;
        box-shadow: 0 3px 10px rgba(0,0,0,0.35);
        white-space: nowrap;
        text-align: center;
      ">${label}</div>
    `;

    const customIcon = L.divIcon({
      html: iconHtml,
      className: "custom-stop-marker",
      iconSize: [isDonor ? 110 : 130, 26],
      iconAnchor: [isDonor ? 55 : 65, 13]
    });

    const marker = L.marker(pos, { icon: customIcon });
    marker.bindPopup(`
      <div style="font-family: sans-serif; font-size: 12.5px; line-height: 1.5; min-width: 180px;">
        <div style="color: ${color}; font-weight: 700; font-size: 11px; text-transform: uppercase;">
          ${isDonor ? '🏢 Pickup Origin' : `📍 Delivery Stop #${idx}`}
        </div>
        <strong style="font-size: 14px; color: #0f172a;">${escapeHtml(s.name)}</strong>
        <div style="color: #64748b; font-size: 12px; margin-top: 2px;">${escapeHtml(s.address)}</div>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 6px 0;">
        <div style="display: flex; justify-content: space-between; font-size: 12px;">
          <span>Estimated Arrival:</span>
          <strong style="color: #059669;">${s.eta_display || s.eta}</strong>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 11.5px; color: #64748b;">
          <span>Cumulative Distance:</span>
          <span>${s.cumulative_distance_km} km</span>
        </div>
      </div>
    `);

    window.FoodLink.markersLayer.addLayer(marker);
  });

  // Render Route Polyline from GeoJSON
  if (routeResult.geojson) {
    const isOsrm = routeResult.is_osrm;

    // Outer casing line for contrast
    const casingLayer = L.geoJSON(routeResult.geojson, {
      style: {
        color: "#065f46",
        weight: 7,
        opacity: 0.4,
        lineCap: "round",
        lineJoin: "round"
      }
    });
    window.FoodLink.routeLayer.addLayer(casingLayer);

    // Main route polyline
    const mainPolyline = L.geoJSON(routeResult.geojson, {
      style: {
        color: isOsrm ? "#10b981" : "#f59e0b",
        dashArray: isOsrm ? null : "6, 8",
        weight: 5,
        opacity: 0.9,
        lineCap: "round",
        lineJoin: "round"
      }
    });
    window.FoodLink.routeLayer.addLayer(mainPolyline);

    map.fitBounds(mainPolyline.getBounds(), { padding: [50, 50] });
  } else if (latLngs.length > 0) {
    map.fitBounds(L.latLngBounds(latLngs), { padding: [50, 50] });
  }

  setTimeout(() => map.invalidateSize(), 150);
}

// Utility escape
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
