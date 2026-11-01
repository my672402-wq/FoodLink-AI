/**
 * FoodLink AI - Core Application Controller
 * Handles SPA navigation, modal dialogs, API helpers, and system state
 */

// Global Application State
window.FoodLink = {
  currentView: "dashboard",
  donors: [],
  ngos: [],
  donations: [],
  activeDonationToMatch: null,
  mapInstance: null,
  routeLayer: null,
  markersLayer: null,
  charts: {}
};

// DOM Content Loaded Handler
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initModals();
  initSystemHealth();
  setDefaultFormDates();

  // Load Initial Core Data
  loadAllAppData();

  // Notification Bell Button in Header
  const btnHeaderNotifs = document.getElementById("btnHeaderNotifs");
  if (btnHeaderNotifs) {
    btnHeaderNotifs.addEventListener("click", () => navigateTo("notifications"));
  }

  // Refresh Seed Demo Data Button
  const btnReset = document.getElementById("btnResetSeed");
  if (btnReset) {
    btnReset.addEventListener("click", resetDemoData);
  }

  // Mobile menu toggle
  const mobileBtn = document.getElementById("mobileMenuBtn");
  const sidebar = document.getElementById("sidebar");
  if (mobileBtn && sidebar) {
    mobileBtn.addEventListener("click", () => {
      sidebar.classList.toggle("mobile-open");
    });
  }
});

// View Navigation Router
function initNavigation() {
  const navItems = document.querySelectorAll(".nav-item");
  navItems.forEach(item => {
    item.addEventListener("click", () => {
      const targetView = item.getAttribute("data-view");
      navigateTo(targetView);
      
      // Close sidebar on mobile
      const sidebar = document.getElementById("sidebar");
      if (sidebar) sidebar.classList.remove("mobile-open");
    });
  });
}

function navigateTo(viewId) {
  window.FoodLink.currentView = viewId;

  // Update active sidebar nav button
  document.querySelectorAll(".nav-item").forEach(item => {
    if (item.getAttribute("data-view") === viewId) {
      item.classList.add("active");
    } else {
      item.classList.remove("active");
    }
  });

  // Switch view section visibility
  document.querySelectorAll(".view-section").forEach(sec => {
    sec.classList.remove("active");
  });

  const activeSec = document.getElementById(`view-${viewId}`);
  if (activeSec) {
    activeSec.classList.add("active");
  }

  // Update Header Title
  updateHeaderTitle(viewId);

  // Trigger view-specific activation hooks
  if (viewId === "dashboard") {
    loadDashboardMetrics();
  } else if (viewId === "donors") {
    loadDonors();
  } else if (viewId === "ngos") {
    loadNgos();
  } else if (viewId === "donations") {
    loadDonations();
  } else if (viewId === "matching") {
    initMatchingView();
  } else if (viewId === "forecasting") {
    initForecastingView();
  } else if (viewId === "routing") {
    initRoutingView();
  } else if (viewId === "food-safety") {
    loadFoodSafetyAudit();
  } else if (viewId === "notifications") {
    loadNotificationsFeed();
  }
}

function updateHeaderTitle(viewId) {
  const titles = {
    "dashboard": { title: "Operations Dashboard", sub: "Real-time surplus food logistics, matching & safety telemetry" },
    "donors": { title: "Food Donor Management", sub: "Register and manage verified food donors across Chandigarh & Mohali" },
    "ngos": { title: "Recipient Organization Directory", sub: "Community kitchens, shelters and family assistance organizations" },
    "donations": { title: "Surplus Food Donations", sub: "Log and track donations with automated safety pre-screening" },
    "matching": { title: "AI Smart Matching Engine", sub: "Multi-factor weighted compatibility scoring & meal allocation" },
    "forecasting": { title: "Demand Forecasting Dashboard", sub: "Statistical moving average projections with Gemini AI commentary" },
    "routing": { title: "OSRM Route Optimization", sub: "Turn-by-turn road driving distances, stop sequences & deadline warnings" },
    "food-safety": { title: "Food Safety Risk Inspector", sub: "Category shelf life verification, temperature danger zones & screening audit" },
    "notifications": { title: "Live Message & Dispatch Telemetry", sub: "Automated SMS alerts (Donors), WhatsApp notifications (NGOs) & Volunteer Road Packets" }
  };

  const meta = titles[viewId] || { title: "FoodLink AI", sub: "Turning Surplus into Support" };
  document.getElementById("currentPageTitle").textContent = meta.title;
  document.getElementById("currentPageSubtitle").textContent = meta.sub;
}

// Modal Controllers
function initModals() {
  // Donor Modal
  const btnOpenDonor = document.getElementById("btnOpenDonorModal");
  if (btnOpenDonor) {
    btnOpenDonor.addEventListener("click", () => openModal("modalDonor"));
  }

  // NGO Modal
  const btnOpenNgo = document.getElementById("btnOpenNgoModal");
  if (btnOpenNgo) {
    btnOpenNgo.addEventListener("click", () => openModal("modalNgo"));
  }

  // Donation Modal
  const btnOpenDon = document.getElementById("btnOpenDonationModal");
  if (btnOpenDon) {
    btnOpenDon.addEventListener("click", () => {
      populateDonorsDropdown("donDonorId");
      setDefaultFormDates();
      openModal("modalDonation");
    });
  }
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add("active");
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove("active");
  }
}

// Quick helper to fill donor sample coordinates
function setDonorCoords(lat, lon, address) {
  document.getElementById("donorLat").value = lat;
  document.getElementById("donorLon").value = lon;
  document.getElementById("donorAddress").value = address;
}

// Health Check & AI Status
async function initSystemHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    const badge = document.getElementById("aiStatusBadge");
    if (badge) {
      if (data.gemini_active) {
        badge.className = "badge badge-success";
        badge.textContent = `✨ Gemini Active (${data.gemini_model})`;
      } else {
        badge.className = "badge badge-neutral";
        badge.textContent = "⚙️ Rule Engine (Fallback)";
      }
    }
  } catch (err) {
    console.error("Health check error:", err);
  }
}

// Populate Default Form Datetime values
function setDefaultFormDates() {
  const now = new Date();
  const prepInput = document.getElementById("donPrepTime");
  const deadInput = document.getElementById("donDeadline");

  if (prepInput) {
    // Prep time = 1 hour ago
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
    prepInput.value = formatDateTimeLocal(oneHourAgo);
  }

  if (deadInput) {
    // Deadline = 3 hours from now
    const threeHoursLater = new Date(now.getTime() + 3 * 60 * 60 * 1000);
    deadInput.value = formatDateTimeLocal(threeHoursLater);
  }
}

function formatDateTimeLocal(d) {
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Reset & Seed Demonstration Data
async function resetDemoData() {
  if (!confirm("Reset database with fresh demonstration data for Chandigarh & Mohali?")) {
    return;
  }
  try {
    const res = await fetch("/api/seed", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      alert("Demonstration database reset successfully!");
      loadAllAppData();
      navigateTo(window.FoodLink.currentView);
    } else {
      alert("Error resetting database: " + data.error);
    }
  } catch (err) {
    alert("Request failed: " + err.message);
  }
}

// Bulk Load Initial Data
async function loadAllAppData() {
  await Promise.all([
    loadDonors(),
    loadNgos(),
    loadDonations(),
    loadDashboardMetrics(),
    loadNotificationsFeed(false)
  ]);
}
