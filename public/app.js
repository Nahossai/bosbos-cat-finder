// Bosbos Cat Finder Frontend App
let allCats = [];
let localFavorites = JSON.parse(localStorage.getItem("bosbos_favorites") || "[]");
let globalLikes = {};
let activeTab = "all";
let activeSort = "most_liked";
let selectedShelter = "all";
let maxAge = 20;
let searchQuery = "";

// Initialize App
document.addEventListener("DOMContentLoaded", async () => {
  initFirebase();
  await loadCats();
  setupEventListeners();
  populateShelterDropdown();
  render();
});

// Firebase Setup (Realtime Database for Community Likes)
let db = null;
function initFirebase() {
  try {
    if (window.FIREBASE_CONFIG && window.FIREBASE_CONFIG.projectId && window.firebase) {
      if (!firebase.apps.length) {
        firebase.initializeApp(window.FIREBASE_CONFIG);
      }
      db = firebase.database();
      db.ref("likes").on("value", (snapshot) => {
        const val = snapshot.val();
        if (val) {
          globalLikes = val;
          render();
        }
      });
    }
  } catch (err) {
    console.warn("Firebase initialization skipped, using local likes:", err);
  }
}

async function loadCats() {
  try {
    const res = await fetch("data/cats.json?t=" + Date.now());
    const data = await res.json();
    allCats = data.cats || [];
    
    // Seed initial likes from local storage if Firebase is absent
    const savedLocalLikes = JSON.parse(localStorage.getItem("bosbos_community_likes") || "{}");
    globalLikes = { ...savedLocalLikes };
    
    // Update stats bar
    const totalEl = document.getElementById("total-cats-count");
    if (totalEl) totalEl.textContent = allCats.length;
    
    const newCount = allCats.filter(c => c.is_new_today).length;
    const newEl = document.getElementById("new-today-count");
    if (newEl) newEl.textContent = newCount;
    
    if (data.updated_at) {
      const dt = new Date(data.updated_at);
      const updatedEl = document.getElementById("last-updated");
      if (updatedEl) {
        updatedEl.textContent = dt.toLocaleDateString() + " " + dt.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
      }
    }
  } catch (err) {
    console.error("Failed to load cats data:", err);
  }
}

function populateShelterDropdown() {
  const shelterEl = document.getElementById("shelter-select");
  if (!shelterEl) return;
  
  const shelters = Array.from(new Set(allCats.map(c => c.shelter).filter(Boolean)));
  // Ensure default standard shelters are in list
  ["MEOW Foundation", "Calgary Humane Society", "Cochrane & Area Humane Society"].forEach(s => {
    if (!shelters.includes(s)) shelters.push(s);
  });
  
  shelterEl.innerHTML = `<option value="all">🏠 All Shelters (${shelters.length} Available)</option>` +
    shelters.map(s => `<option value="${s}">${s}</option>`).join("");
}

function setupEventListeners() {
  // Search Input
  const searchEl = document.getElementById("search-input");
  if (searchEl) {
    searchEl.addEventListener("input", (e) => {
      searchQuery = e.target.value.toLowerCase().trim();
      render();
    });
  }

  // Shelter Select
  const shelterEl = document.getElementById("shelter-select");
  if (shelterEl) {
    shelterEl.addEventListener("change", (e) => {
      selectedShelter = e.target.value;
      render();
    });
  }

  // Sort Dropdown
  const sortEl = document.getElementById("sort-select");
  if (sortEl) {
    sortEl.addEventListener("change", (e) => {
      activeSort = e.target.value;
      render();
    });
  }

  // Filter Tabs
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeTab = btn.dataset.tab;
      render();
    });
  });

  // Age Slider
  const sliderEl = document.getElementById("age-slider");
  const ageDisplayEl = document.getElementById("age-val");
  if (sliderEl) {
    sliderEl.addEventListener("input", (e) => {
      maxAge = parseFloat(e.target.value);
      if (ageDisplayEl) ageDisplayEl.textContent = `${maxAge} wks`;
      render();
    });
  }

  // Share Button
  const shareBtn = document.getElementById("share-btn");
  if (shareBtn) {
    shareBtn.addEventListener("click", shareWithFriends);
  }

  // Modal Close
  const modalClose = document.getElementById("modal-close");
  const modalOverlay = document.getElementById("modal-overlay");
  if (modalClose && modalOverlay) {
    modalClose.addEventListener("click", () => modalOverlay.classList.remove("active"));
    modalOverlay.addEventListener("click", (e) => {
      if (e.target === modalOverlay) modalOverlay.classList.remove("active");
    });
  }
}

function toggleLike(catId) {
  const isCurrentlyFav = localFavorites.includes(catId);
  const currentLikes = globalLikes[catId] || 0;
  
  if (isCurrentlyFav) {
    localFavorites = localFavorites.filter(id => id !== catId);
    globalLikes[catId] = Math.max(0, currentLikes - 1);
  } else {
    localFavorites.push(catId);
    globalLikes[catId] = currentLikes + 1;
  }
  
  localStorage.setItem("bosbos_favorites", JSON.stringify(localFavorites));
  localStorage.setItem("bosbos_community_likes", JSON.stringify(globalLikes));
  
  if (db) {
    db.ref("likes/" + catId).set(globalLikes[catId]);
  }
  
  render();
}

function shareWithFriends() {
  const shareData = {
    title: "Help me find Bosbos! 🐾",
    text: "Hey! I'm planning to adopt a kitten named Bosbos in December. Check out the shortlisted kittens in Calgary and vote for your favorites!",
    url: window.location.href
  };

  if (navigator.share) {
    navigator.share(shareData).catch(() => {});
  } else {
    navigator.clipboard.writeText(window.location.href).then(() => {
      alert("🐾 Link copied to clipboard! Share it with friends to vote on kittens.");
    });
  }
}

function openModal(cat) {
  const modalOverlay = document.getElementById("modal-overlay");
  const modalTitle = document.getElementById("modal-title");
  const modalBody = document.getElementById("modal-body");
  
  modalTitle.textContent = `${cat.name} — ${cat.shelter}`;
  modalBody.innerHTML = `
    <div style="display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap;">
      <img src="${cat.image_url}" alt="${cat.name}" style="width: 160px; height: 160px; object-fit: cover; border-radius: 14px;" />
      <div style="flex: 1; min-width: 200px;">
        <p style="margin-bottom: 6px;"><strong>Age:</strong> ${cat.age_str} (~${cat.age_weeks} weeks)</p>
        <p style="margin-bottom: 6px;"><strong>Sex:</strong> ${cat.sex}</p>
        <p style="margin-bottom: 6px;"><strong>Breed:</strong> ${cat.breed || 'Rescue Mix'}</p>
        <p style="margin-bottom: 6px;"><strong>Color:</strong> ${cat.color_category}</p>
        <p style="margin-bottom: 6px;"><strong>Shelter:</strong> ${cat.shelter} (${cat.shelter_location || 'Calgary'})</p>
        <p style="margin-bottom: 6px;"><strong>Phone:</strong> ${cat.shelter_phone || 'See website'}</p>
        <p style="margin-bottom: 6px;"><strong>Bosbos Score:</strong> <span style="color: #f43f5e; font-weight: bold;">${cat.bosbos_score}/100</span></p>
      </div>
    </div>
    <div style="background: #f8fafc; padding: 14px; border-radius: 12px; margin-bottom: 16px; font-size: 14px; line-height: 1.6; color: #334155;">
      <strong>Bio & Personality:</strong><br/>
      ${cat.bio || 'Gentle and lovely kitten ready for meeting and adoption.'}
    </div>
    <a href="${cat.adoption_url}" target="_blank" class="btn-adopt" style="display: block; text-align: center;">
      Apply to Adopt ${cat.name} on Shelter Website →
    </a>
  `;
  modalOverlay.classList.add("active");
}

function render() {
  const gridEl = document.getElementById("cats-grid");
  if (!gridEl) return;

  // 1. Filter
  let filtered = allCats.filter(cat => {
    // Shelter filter
    if (selectedShelter !== "all" && cat.shelter !== selectedShelter) {
      return false;
    }

    // Age check
    if (cat.age_weeks && cat.age_weeks > maxAge) return false;

    // Search query
    if (searchQuery) {
      const matchText = [cat.name, cat.shelter, cat.breed, cat.bio, cat.color_category].join(" ").toLowerCase();
      if (!matchText.includes(searchQuery)) return false;
    }

    // Tabs
    const likesCount = globalLikes[cat.id] || 0;
    const isFav = localFavorites.includes(cat.id);

    if (activeTab === "liked" && likesCount <= 0) return false;
    if (activeTab === "favorites" && !isFav) return false;
    if (activeTab === "new" && !cat.is_new_today) return false;
    if (activeTab === "white" && !cat.color_category.toLowerCase().includes("white") && !cat.color_category.toLowerCase().includes("cream")) return false;

    return true;
  });

  // 2. Sort
  filtered.sort((a, b) => {
    const likesA = globalLikes[a.id] || 0;
    const likesB = globalLikes[b.id] || 0;

    if (activeSort === "most_liked") {
      if (likesB !== likesA) return likesB - likesA;
      return b.bosbos_score - a.bosbos_score;
    }
    if (activeSort === "score") {
      return b.bosbos_score - a.bosbos_score;
    }
    if (activeSort === "youngest") {
      return (a.age_weeks || 99) - (b.age_weeks || 99);
    }
    if (activeSort === "newest") {
      return (b.is_new_today ? 1 : 0) - (a.is_new_today ? 1 : 0);
    }
    return 0;
  });

  // 3. Render Cards
  if (filtered.length === 0) {
    gridEl.innerHTML = `
      <div class="empty-state">
        <h3>No kittens matching current filters 🐾</h3>
        <p>Try switching the shelter filter or adjusting the age slider.</p>
      </div>
    `;
    return;
  }

  gridEl.innerHTML = filtered.map(cat => {
    const likesCount = globalLikes[cat.id] || 0;
    const isLiked = localFavorites.includes(cat.id);
    const cuteTagsHtml = (cat.cute_tags || [])
      .map(tag => `<span class="cute-tag">✨ ${tag}</span>`)
      .join("");

    return `
      <div class="cat-card" id="card-${cat.id}">
        <div class="card-image-wrap">
          <img class="card-image" src="${cat.image_url || 'https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?auto=format&fit=crop&w=600&q=80'}" alt="${cat.name}" loading="lazy" />
          ${cat.is_new_today ? '<span class="badge-new">NEW TODAY</span>' : ''}
          <span class="badge-score">⭐ ${cat.bosbos_score}% Match</span>
        </div>
        <div class="card-content">
          <div class="card-header-row">
            <h2 class="cat-name">${cat.name}</h2>
            <button class="like-btn ${isLiked ? 'liked' : ''}" onclick="toggleLike('${cat.id}')" title="Vote for ${cat.name}">
              <span>${isLiked ? '❤️' : '🤍'}</span>
              <span id="likes-count-${cat.id}">${likesCount}</span>
            </button>
          </div>
          <div class="info-pills">
            <span class="pill pill-age">🍼 ${cat.age_str} (~${cat.age_weeks} wks)</span>
            <span class="pill pill-shelter">🏠 ${cat.shelter}</span>
            <span class="pill pill-palette">🎨 ${cat.color_category}</span>
          </div>
          <p class="cat-bio">${cat.bio || 'Gentle and affectionate kitten available for adoption in Calgary.'}</p>
          <div class="cute-tags">${cuteTagsHtml}</div>
          <div class="card-actions">
            <button class="btn-details" onclick='openModal(${JSON.stringify(cat).replace(/'/g, "&apos;")})'>Details</button>
            <a href="${cat.adoption_url}" target="_blank" rel="noopener noreferrer" class="btn-adopt">Meet / Apply →</a>
          </div>
        </div>
      </div>
    `;
  }).join("");
}
