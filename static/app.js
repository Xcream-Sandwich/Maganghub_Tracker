// MagangHub Tracker State & Multi-Select Manager
let state = {
  keyword: '',
  province_ids: [],
  city_names: [],
  district_name: '',
  study_program: '',
  education_levels: [],
  organizer_types: [],
  organizer_name: '',
  min_quota: 0,
  sort_by: 'terbaru',
  page: 1,
  limit: 18,
  total_pages: 1,
  total: 0
};

let filterOptions = {
  provinces: [],
  cities: []
};

let debounceTimer = null;
let leafletMap = null;
let mapMarker = null;

document.addEventListener('DOMContentLoaded', async () => {
  lucide.createIcons();
  loadQueryParamsFromUrl();
  await loadFilterOptions();
  await loadMetadata();
  await fetchVacancies();
  setupEventListeners();
});

// Load Query Params
function loadQueryParamsFromUrl() {
  const params = new URLSearchParams(window.location.search);
  if (params.has('kw')) state.keyword = params.get('kw');
  if (params.has('prov')) state.province_ids = params.get('prov').split(',').filter(Boolean);
  if (params.has('city')) state.city_names = params.get('city').split(',').filter(Boolean);
  if (params.has('dist')) state.district_name = params.get('dist');
  if (params.has('study')) state.study_program = params.get('study');
  if (params.has('edu')) state.education_levels = params.get('edu').split(',').filter(Boolean);
  if (params.has('org_type')) state.organizer_types = params.get('org_type').split(',').filter(Boolean);
  if (params.has('org_name')) state.organizer_name = params.get('org_name');
  if (params.has('min_q')) state.min_quota = parseInt(params.get('min_q')) || 0;
  if (params.has('sort')) state.sort_by = params.get('sort');
  if (params.has('p')) state.page = parseInt(params.get('p')) || 1;

  // Sync inputs
  document.getElementById('search-keyword').value = state.keyword;
  document.getElementById('filter-district').value = state.district_name;
  document.getElementById('filter-study').value = state.study_program;
  document.getElementById('filter-company').value = state.organizer_name;
  document.getElementById('filter-min-quota').value = state.min_quota;
  document.getElementById('min-quota-val').innerText = state.min_quota;
  document.getElementById('sort-select').value = state.sort_by;

  // Checkboxes
  document.querySelectorAll('#edu-options input[type="checkbox"]').forEach(cb => {
    cb.checked = state.education_levels.includes(cb.value);
  });
  document.querySelectorAll('#org-type-options input[type="checkbox"]').forEach(cb => {
    cb.checked = state.organizer_types.includes(cb.value);
  });
}

// Sync to URL
function syncUrlWithState() {
  const params = new URLSearchParams();
  if (state.keyword) params.set('kw', state.keyword);
  if (state.province_ids.length) params.set('prov', state.province_ids.join(','));
  if (state.city_names.length) params.set('city', state.city_names.join(','));
  if (state.district_name) params.set('dist', state.district_name);
  if (state.study_program) params.set('study', state.study_program);
  if (state.education_levels.length) params.set('edu', state.education_levels.join(','));
  if (state.organizer_types.length) params.set('org_type', state.organizer_types.join(','));
  if (state.organizer_name) params.set('org_name', state.organizer_name);
  if (state.min_quota > 0) params.set('min_q', state.min_quota);
  if (state.sort_by !== 'terbaru') params.set('sort', state.sort_by);
  if (state.page > 1) params.set('p', state.page);

  const newUrl = window.location.pathname + (params.toString() ? '?' + params.toString() : '');
  window.history.replaceState({}, '', newUrl);
}

// Metadata
async function loadMetadata() {
  try {
    const res = await fetch('/api/meta');
    const data = await res.json();
    const metaBadge = document.getElementById('sync-meta-badge');
    const genAt = data.sync_meta?.generated_at?.value;
    const formattedDate = genAt ? new Date(genAt).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }) : 'Online';
    metaBadge.innerHTML = `<span class="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1.5 animate-pulse"></span>Total: <strong>${data.total_vacancies?.toLocaleString('id-ID') || 0}</strong> lowongan (Kemnaker Sync: ${formattedDate})`;
  } catch (e) {
    console.error('Error loading meta:', e);
  }
}

// Filter Options (Provinces & Cities)
async function loadFilterOptions() {
  try {
    const res = await fetch('/api/filters');
    filterOptions = await res.json();
    renderProvinceList();
    renderCityList();
  } catch (e) {
    console.error('Error loading filters:', e);
  }
}

// Render Province Checkbox List
function renderProvinceList(searchTerm = '') {
  const listContainer = document.getElementById('prov-checkbox-list');
  const term = searchTerm.toLowerCase();
  const filtered = filterOptions.provinces.filter(p => p.name.toLowerCase().includes(term));

  listContainer.innerHTML = filtered.map(p => `
    <label class="flex items-center gap-2 p-1 hover:bg-slate-50 rounded cursor-pointer text-xs">
      <input type="checkbox" value="${p.id}" ${state.province_ids.includes(p.id) ? 'checked' : ''} class="prov-cb accent-indigo-600 rounded">
      <span class="text-slate-700">${escapeHtml(p.name)}</span>
    </label>
  `).join('') || '<p class="text-[11px] text-slate-400 p-1">Provinsi tidak ditemukan</p>';

  // Attach change
  listContainer.querySelectorAll('.prov-cb').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const pId = e.target.value;
      if (e.target.checked) {
        if (!state.province_ids.includes(pId)) state.province_ids.push(pId);
      } else {
        state.province_ids = state.province_ids.filter(id => id !== pId);
      }
      updateProvinceUI();
      renderCityList();
      state.page = 1;
      fetchVacancies();
    });
  });

  updateProvinceUI();
}

function updateProvinceUI() {
  const count = state.province_ids.length;
  const label = document.getElementById('prov-selected-label');
  const badge = document.getElementById('badge-count-prov');
  const chips = document.getElementById('prov-selected-chips');

  if (count === 0) {
    label.innerText = 'Pilih Provinsi...';
    badge.classList.add('hidden');
    chips.innerHTML = '';
  } else {
    label.innerText = `${count} Provinsi Dipilih`;
    badge.innerText = `${count} terpilih`;
    badge.classList.remove('hidden');

    chips.innerHTML = state.province_ids.map(id => {
      const p = filterOptions.provinces.find(item => item.id === id);
      const name = p ? p.name : id;
      return `
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-200">
          ${escapeHtml(name)}
          <button type="button" onclick="removeProvince('${id}')" class="hover:text-indigo-900 font-bold">&times;</button>
        </span>
      `;
    }).join('');
  }
}

window.removeProvince = (id) => {
  state.province_ids = state.province_ids.filter(item => item !== id);
  renderProvinceList();
  renderCityList();
  state.page = 1;
  fetchVacancies();
};

// Render City Checkbox List
function renderCityList(searchTerm = '') {
  const listContainer = document.getElementById('city-checkbox-list');
  const term = searchTerm.toLowerCase();

  let availableCities = filterOptions.cities;
  if (state.province_ids.length > 0) {
    availableCities = availableCities.filter(c => state.province_ids.includes(c.province_id));
  }

  const uniqueNames = Array.from(new Set(availableCities.map(c => c.city_name))).sort();
  const filtered = uniqueNames.filter(name => name.toLowerCase().includes(term));

  listContainer.innerHTML = filtered.map(name => `
    <label class="flex items-center gap-2 p-1 hover:bg-slate-50 rounded cursor-pointer text-xs">
      <input type="checkbox" value="${escapeHtml(name)}" ${state.city_names.includes(name) ? 'checked' : ''} class="city-cb accent-indigo-600 rounded">
      <span class="text-slate-700">${escapeHtml(name)}</span>
    </label>
  `).join('') || '<p class="text-[11px] text-slate-400 p-1">Kota tidak ditemukan</p>';

  listContainer.querySelectorAll('.city-cb').forEach(cb => {
    cb.addEventListener('change', (e) => {
      const val = e.target.value;
      if (e.target.checked) {
        if (!state.city_names.includes(val)) state.city_names.push(val);
      } else {
        state.city_names = state.city_names.filter(item => item !== val);
      }
      updateCityUI();
      state.page = 1;
      fetchVacancies();
    });
  });

  updateCityUI();
}

function updateCityUI() {
  const count = state.city_names.length;
  const label = document.getElementById('city-selected-label');
  const badge = document.getElementById('badge-count-city');
  const chips = document.getElementById('city-selected-chips');

  if (count === 0) {
    label.innerText = 'Pilih Kota/Kabupaten...';
    badge.classList.add('hidden');
    chips.innerHTML = '';
  } else {
    label.innerText = `${count} Kota/Kab Dipilih`;
    badge.innerText = `${count} terpilih`;
    badge.classList.remove('hidden');

    chips.innerHTML = state.city_names.map(name => `
      <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-slate-100 text-slate-700 border border-slate-200">
        ${escapeHtml(name)}
        <button type="button" onclick="removeCity('${escapeHtml(name)}')" class="hover:text-slate-900 font-bold">&times;</button>
      </span>
    `).join('');
  }
}

window.removeCity = (name) => {
  state.city_names = state.city_names.filter(item => item !== name);
  renderCityList();
  state.page = 1;
  fetchVacancies();
};

// Fetch Vacancies
async function fetchVacancies() {
  const listContainer = document.getElementById('vacancy-list');
  listContainer.innerHTML = `
    <div class="col-span-full py-16 text-center text-slate-400">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-4 border-indigo-500 border-t-transparent mb-2"></div>
      <p class="text-xs">Memuat lowongan magang...</p>
    </div>
  `;

  syncUrlWithState();
  renderActiveChips();

  const params = new URLSearchParams({
    page: state.page,
    limit: state.limit,
    sort_by: state.sort_by
  });
  if (state.keyword) params.append('keyword', state.keyword);
  state.province_ids.forEach(p => params.append('province_id', p));
  state.city_names.forEach(c => params.append('city_name', c));
  if (state.district_name) params.append('district_name', state.district_name);
  if (state.study_program) {
    state.study_program.split(',').map(s => s.trim()).filter(Boolean).forEach(sp => params.append('study_program', sp));
  }
  state.education_levels.forEach(e => params.append('education_level', e));
  state.organizer_types.forEach(ot => params.append('organizer_type', ot));
  if (state.organizer_name) params.append('organizer_name', state.organizer_name);
  if (state.min_quota > 0) params.append('min_quota', state.min_quota);

  try {
    const res = await fetch(`/api/vacancies?${params.toString()}`);
    const data = await res.json();
    state.total = data.total;
    state.total_pages = data.total_pages;

    document.getElementById('results-count').innerText = data.total.toLocaleString('id-ID');
    renderVacancyCards(data.items);
    renderPagination();
  } catch (e) {
    listContainer.innerHTML = `
      <div class="col-span-full py-12 text-center text-rose-500">
        <p class="text-sm font-semibold">Gagal memuat lowongan.</p>
        <p class="text-xs text-slate-500 mt-1">${e.message}</p>
      </div>
    `;
  }
}

// Render Cards
function renderVacancyCards(items) {
  const container = document.getElementById('vacancy-list');
  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-16 text-center bg-white rounded-2xl border border-slate-200">
        <i data-lucide="inbox" class="w-10 h-10 mx-auto text-slate-300 mb-2"></i>
        <p class="text-sm font-semibold text-slate-700">Tidak ada lowongan yang cocok.</p>
        <p class="text-xs text-slate-400 mt-1">Cobalah mengurangi filter atau memilih opsi lain.</p>
      </div>
    `;
    lucide.createIcons();
    return;
  }

  container.innerHTML = items.map(item => {
    const pubDate = item.published_at ? new Date(item.published_at).toLocaleDateString('id-ID', { day: 'numeric', month: 'short', year: 'numeric' }) : '-';
    const oppScore = item.opportunity_score !== undefined ? Math.round(item.opportunity_score) : 80;
    const quota = item.approved_quantity || item.quantity_needed || 1;
    const apps = item.total_applications || 0;
    const remaining = Math.max(0, quota - apps);

    // Color code based on real opportunity
    let oppColor = 'text-emerald-600 bg-emerald-50 border-emerald-200';
    if (oppScore < 40) {
      oppColor = 'text-rose-600 bg-rose-50 border-rose-200';
    } else if (oppScore < 70) {
      oppColor = 'text-amber-600 bg-amber-50 border-amber-200';
    }

    const progs = (item.study_programs || []).map(p => typeof p === 'object' ? p.name : p);
    const progText = progs.slice(0, 2).join(', ') + (progs.length > 2 ? ` +${progs.length - 2}` : '');
    const locText = [item.district_name ? 'Kec. ' + item.district_name : '', item.city_name, item.province_name].filter(Boolean).join(', ') || 'Indonesia';

    return `
      <div class="bg-white rounded-2xl border border-slate-200 p-5 hover:shadow-lg hover:border-indigo-200 transition-all flex flex-col justify-between group cursor-pointer" onclick="openDetailModal('${item.id}')">
        <div class="space-y-3">
          <!-- Top Tag & Date -->
          <div class="flex items-center justify-between text-[11px]">
            <span class="px-2 py-0.5 rounded-full font-medium ${item.organizer_type === 'Kementerian/Lembaga' ? 'bg-amber-50 text-amber-700 border border-amber-200/60' : 'bg-indigo-50 text-indigo-700 border border-indigo-200/60'}">
              ${item.organizer_type || 'Perusahaan'}
            </span>
            <span class="text-slate-400 font-normal">${pubDate}</span>
          </div>

          <!-- Title & Company -->
          <div>
            <h3 class="font-bold text-slate-900 group-hover:text-indigo-600 transition-colors text-sm sm:text-base line-clamp-2 leading-snug">
              ${escapeHtml(item.position_name || item.title)}
            </h3>
            <p class="text-xs font-semibold text-slate-600 mt-1 flex items-center gap-1">
              <i data-lucide="building" class="w-3.5 h-3.5 text-slate-400 shrink-0"></i>
              ${escapeHtml(item.organizer_name || 'Instansi')}
            </p>
          </div>

          <!-- Location -->
          <p class="text-[11px] text-slate-500 flex items-center gap-1 line-clamp-1">
            <i data-lucide="map-pin" class="w-3.5 h-3.5 text-slate-400 shrink-0"></i>
            ${escapeHtml(locText)}
          </p>

          <!-- Education & Major -->
          <div class="flex flex-wrap gap-1 text-[10px]">
            ${(item.education_levels || []).map(e => `<span class="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">${escapeHtml(e)}</span>`).join('')}
            ${progText ? `<span class="px-2 py-0.5 rounded bg-slate-50 text-slate-500 border border-slate-100" title="${escapeHtml(progs.join(', '))}">${escapeHtml(progText)}</span>` : ''}
          </div>
        </div>

        <!-- Metrics Footer -->
        <div class="pt-4 mt-3 border-t border-slate-100 flex items-center justify-between text-xs">
          <div class="flex items-center gap-3">
            <div title="Kuota yang disetujui">
              <span class="text-[10px] text-slate-400 block">Kuota</span>
              <span class="font-bold text-slate-800">${quota}</span>
            </div>
            <div title="Jumlah pelamar saat ini">
              <span class="text-[10px] text-slate-400 block">Pelamar</span>
              <span class="font-bold text-slate-600">${apps}</span>
            </div>
            <div title="Sisa kuota">
              <span class="text-[10px] text-slate-400 block">Sisa Slot</span>
              <span class="font-bold ${remaining > 0 ? 'text-indigo-600' : 'text-slate-400'}">${remaining}</span>
            </div>
          </div>

          <div class="text-right" title="Peluang Diterima Realistis">
            <span class="text-[10px] text-slate-400 block font-medium">Peluang</span>
            <span class="font-extrabold text-xs px-2 py-0.5 rounded-md border ${oppColor}">${oppScore}%</span>
          </div>
        </div>
      </div>
    `;
  }).join('');

  lucide.createIcons();
}

// Active Chips
function renderActiveChips() {
  const container = document.getElementById('active-chips');
  const chips = [];

  if (state.keyword) chips.push({ label: `Kata kunci: ${state.keyword}`, remove: () => { state.keyword = ''; document.getElementById('search-keyword').value = ''; } });
  
  if (state.province_ids.length > 0) {
    chips.push({
      label: `Provinsi: ${state.province_ids.length} dipilih`,
      remove: () => { state.province_ids = []; renderProvinceList(); renderCityList(); }
    });
  }

  if (state.city_names.length > 0) {
    chips.push({
      label: `Kota: ${state.city_names.length} dipilih`,
      remove: () => { state.city_names = []; renderCityList(); }
    });
  }

  if (state.district_name) chips.push({ label: `Kec: ${state.district_name}`, remove: () => { state.district_name = ''; document.getElementById('filter-district').value = ''; } });
  if (state.study_program) chips.push({ label: `Prodi: ${state.study_program}`, remove: () => { state.study_program = ''; document.getElementById('filter-study').value = ''; } });
  
  if (state.education_levels.length > 0) {
    chips.push({
      label: `Jenjang: ${state.education_levels.join(', ')}`,
      remove: () => {
        state.education_levels = [];
        document.querySelectorAll('#edu-options input[type="checkbox"]').forEach(cb => cb.checked = false);
      }
    });
  }

  if (state.organizer_types.length > 0) {
    chips.push({
      label: `Jenis: ${state.organizer_types.join(', ')}`,
      remove: () => {
        state.organizer_types = [];
        document.querySelectorAll('#org-type-options input[type="checkbox"]').forEach(cb => cb.checked = false);
      }
    });
  }

  if (state.organizer_name) chips.push({ label: `Instansi: ${state.organizer_name}`, remove: () => { state.organizer_name = ''; document.getElementById('filter-company').value = ''; } });
  if (state.min_quota > 0) chips.push({ label: `Min. Kuota: ${state.min_quota}`, remove: () => { state.min_quota = 0; document.getElementById('filter-min-quota').value = 0; document.getElementById('min-quota-val').innerText = '0'; } });

  container.innerHTML = chips.map((c, i) => `
    <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
      ${escapeHtml(c.label)}
      <button type="button" onclick="removeChip(${i})" class="hover:text-indigo-900">&times;</button>
    </span>
  `).join('');

  window._activeChipsList = chips;
}

window.removeChip = (idx) => {
  if (window._activeChipsList && window._activeChipsList[idx]) {
    window._activeChipsList[idx].remove();
    state.page = 1;
    fetchVacancies();
  }
};

// Pagination
function renderPagination() {
  const container = document.getElementById('pagination');
  if (state.total_pages <= 1) {
    container.innerHTML = '';
    return;
  }

  let html = `
    <button onclick="goToPage(${state.page - 1})" ${state.page === 1 ? 'disabled class="opacity-40 cursor-not-allowed"' : ''} class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium hover:bg-slate-50 transition-colors">
      &larr; Prev
    </button>
    <span class="text-xs font-medium text-slate-600 px-2">Halaman ${state.page} dari ${state.total_pages}</span>
    <button onclick="goToPage(${state.page + 1})" ${state.page >= state.total_pages ? 'disabled class="opacity-40 cursor-not-allowed"' : ''} class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium hover:bg-slate-50 transition-colors">
      Next &rarr;
    </button>
  `;
  container.innerHTML = html;
}

window.goToPage = (p) => {
  if (p < 1 || p > state.total_pages) return;
  state.page = p;
  fetchVacancies();
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

// Modal Detail
window.openDetailModal = async (vId) => {
  try {
    const res = await fetch(`/api/vacancies/${vId}`);
    if (!res.ok) throw new Error('Lowongan tidak ditemukan');
    const v = await res.json();

    document.getElementById('modal-title').innerText = v.position_name || v.title || '';
    document.getElementById('modal-company-name').innerText = v.organizer_name || '';
    document.getElementById('modal-org-type').innerText = v.organizer_type || 'Perusahaan';
    
    // Logo
    const logoContainer = document.getElementById('modal-company-logo');
    if (v.company_logo) {
      logoContainer.innerHTML = `<img src="${v.company_logo}" class="max-h-full max-w-full object-contain" alt="Logo" onerror="this.onerror=null;this.parentElement.innerHTML='<i data-lucide=\'building-2\' class=\'w-6 h-6 text-indigo-600\'></i>';lucide.createIcons();">`;
    } else {
      logoContainer.innerHTML = `<i data-lucide="building-2" class="w-6 h-6 text-indigo-600"></i>`;
    }

    // Stats
    const quota = v.approved_quantity || v.quantity_needed || 1;
    const apps = v.total_applications || 0;
    const remaining = Math.max(0, quota - apps);
    const oppScore = v.opportunity_score !== undefined ? Math.round(v.opportunity_score) : 80;

    document.getElementById('modal-approved-qty').innerText = quota;
    document.getElementById('modal-applications').innerText = apps.toLocaleString('id-ID');
    document.getElementById('modal-opportunity').innerText = oppScore + '%';
    document.getElementById('modal-remaining-slot').innerText = remaining;

    // UMK Card
    const umkContainer = document.getElementById('umk-card-container');
    if (v.umk_estimation && v.umk_estimation.value) {
      umkContainer.classList.remove('hidden');
      document.getElementById('umk-amount').innerText = 'Rp ' + Number(v.umk_estimation.value).toLocaleString('id-ID');
      document.getElementById('umk-area-name').innerText = `${v.umk_estimation.type}: ${v.umk_estimation.area_name}`;
      document.getElementById('umk-badge-year').innerText = v.umk_estimation.year || 2026;
    } else {
      umkContainer.classList.remove('hidden');
      document.getElementById('umk-amount').innerText = 'Data belum tersedia';
      document.getElementById('umk-area-name').innerText = 'Data referensi UMK untuk wilayah ini belum terdaftar di basis data.';
    }

    // Edu & Study
    document.getElementById('modal-edu-levels').innerHTML = (v.education_levels || []).map(e => `<span class="px-2.5 py-1 rounded-md bg-indigo-50 text-indigo-700 font-semibold text-xs border border-indigo-100">${escapeHtml(e)}</span>`).join('') || '-';
    
    const studyList = (v.study_programs || []).map(p => typeof p === 'object' ? p.name : p);
    document.getElementById('modal-study-programs').innerHTML = studyList.map(s => `<span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-xs">${escapeHtml(s)}</span>`).join('') || '<span class="text-slate-400">Semua Jurusan</span>';

    // Working info
    document.getElementById('modal-working-days').innerText = `${v.working_days_per_week || 5} hari kerja per minggu`;
    document.getElementById('modal-interview-types').innerText = `Metode Seleksi: ${(v.interview_types || []).join(', ') || 'Onsite'}`;

    // Location
    const locFull = [v.address, v.district_name ? 'Kec. ' + v.district_name : '', v.city_name, v.province_name].filter(Boolean).join(', ');
    document.getElementById('modal-location').innerText = locFull || 'Alamat tidak tertera';

    // Description
    document.getElementById('modal-task-desc').innerText = v.task_description || 'Tidak ada deskripsi detail pekerjaan.';

    // Date & Link
    const pubDate = v.published_at ? new Date(v.published_at).toLocaleDateString('id-ID', { day: 'numeric', month: 'long', year: 'numeric' }) : '-';
    document.getElementById('modal-pub-date').innerText = pubDate;
    document.getElementById('modal-official-link').href = v.url || `https://maganghub.kemnaker.go.id/lowongan/${v.id}`;

    // Map
    const mapWrap = document.getElementById('modal-map-container');
    if (v.latitude && v.longitude && !isNaN(v.latitude) && !isNaN(v.longitude)) {
      mapWrap.classList.remove('hidden');
      setTimeout(() => {
        if (!leafletMap) {
          leafletMap = L.map('modal-map').setView([v.latitude, v.longitude], 13);
          L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
          }).addTo(leafletMap);
        } else {
          leafletMap.setView([v.latitude, v.longitude], 13);
          leafletMap.invalidateSize();
        }
        if (mapMarker) mapMarker.remove();
        mapMarker = L.marker([v.latitude, v.longitude]).addTo(leafletMap)
          .bindPopup(`<strong>${escapeHtml(v.organizer_name || '')}</strong><br>${escapeHtml(v.position_name || '')}`).openPopup();
      }, 200);
    } else {
      mapWrap.classList.add('hidden');
    }

    document.getElementById('detail-modal').classList.remove('hidden');
    lucide.createIcons();
  } catch (err) {
    alert('Gagal membuka detail lowongan: ' + err.message);
  }
};

// Setup Event Listeners
function setupEventListeners() {
  // Dropdown toggles
  const btnProv = document.getElementById('dropdown-btn-prov');
  const menuProv = document.getElementById('dropdown-menu-prov');
  const btnCity = document.getElementById('dropdown-btn-city');
  const menuCity = document.getElementById('dropdown-menu-city');

  btnProv.addEventListener('click', (e) => {
    e.stopPropagation();
    menuProv.classList.toggle('hidden');
    menuCity.classList.add('hidden');
  });

  btnCity.addEventListener('click', (e) => {
    e.stopPropagation();
    menuCity.classList.toggle('hidden');
    menuProv.classList.add('hidden');
  });

  document.addEventListener('click', (e) => {
    if (!menuProv.contains(e.target) && !btnProv.contains(e.target)) menuProv.classList.add('hidden');
    if (!menuCity.contains(e.target) && !btnCity.contains(e.target)) menuCity.classList.add('hidden');
  });

  // Search inside dropdowns
  document.getElementById('search-prov-input').addEventListener('input', (e) => {
    renderProvinceList(e.target.value);
  });

  document.getElementById('search-city-input').addEventListener('input', (e) => {
    renderCityList(e.target.value);
  });

  // Education level multi-checkboxes
  document.querySelectorAll('#edu-options input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => {
      state.education_levels = Array.from(document.querySelectorAll('#edu-options input[type="checkbox"]:checked')).map(c => c.value);
      state.page = 1;
      fetchVacancies();
    });
  });

  // Organizer type multi-checkboxes
  document.querySelectorAll('#org-type-options input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => {
      state.organizer_types = Array.from(document.querySelectorAll('#org-type-options input[type="checkbox"]:checked')).map(c => c.value);
      state.page = 1;
      fetchVacancies();
    });
  });

  // Search keyword debounced
  document.getElementById('search-keyword').addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.keyword = e.target.value.trim();
      state.page = 1;
      fetchVacancies();
    }, 350);
  });

  // District input
  document.getElementById('filter-district').addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.district_name = e.target.value.trim();
      state.page = 1;
      fetchVacancies();
    }, 400);
  });

  // Study program input
  document.getElementById('filter-study').addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.study_program = e.target.value.trim();
      state.page = 1;
      fetchVacancies();
    }, 400);
  });

  // Company input
  document.getElementById('filter-company').addEventListener('input', (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.organizer_name = e.target.value.trim();
      state.page = 1;
      fetchVacancies();
    }, 400);
  });

  // Min quota range
  document.getElementById('filter-min-quota').addEventListener('input', (e) => {
    state.min_quota = parseInt(e.target.value) || 0;
    document.getElementById('min-quota-val').innerText = state.min_quota;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.page = 1;
      fetchVacancies();
    }, 300);
  });

  // Sort change
  document.getElementById('sort-select').addEventListener('change', (e) => {
    state.sort_by = e.target.value;
    state.page = 1;
    fetchVacancies();
  });

  // Reset filters
  document.getElementById('btn-reset-filters').addEventListener('click', () => {
    state.keyword = '';
    state.province_ids = [];
    state.city_names = [];
    state.district_name = '';
    state.study_program = '';
    state.education_levels = [];
    state.organizer_types = [];
    state.organizer_name = '';
    state.min_quota = 0;
    state.page = 1;
    state.sort_by = 'terbaru';

    document.getElementById('search-keyword').value = '';
    document.getElementById('filter-district').value = '';
    document.getElementById('filter-study').value = '';
    document.getElementById('filter-company').value = '';
    document.getElementById('filter-min-quota').value = 0;
    document.getElementById('min-quota-val').innerText = '0';
    document.getElementById('sort-select').value = 'terbaru';
    
    document.querySelectorAll('#edu-options input[type="checkbox"]').forEach(cb => cb.checked = false);
    document.querySelectorAll('#org-type-options input[type="checkbox"]').forEach(cb => cb.checked = false);

    renderProvinceList();
    renderCityList();
    fetchVacancies();
  });

  // Modal close
  document.getElementById('btn-close-modal').addEventListener('click', () => {
    document.getElementById('detail-modal').classList.add('hidden');
  });

  document.getElementById('detail-modal').addEventListener('click', (e) => {
    if (e.target.id === 'detail-modal') {
      document.getElementById('detail-modal').classList.add('hidden');
    }
  });

  // Sync button
  document.getElementById('btn-sync').addEventListener('click', async () => {
    const icon = document.getElementById('sync-icon');
    const txt = document.getElementById('sync-btn-text');
    icon.classList.add('animate-spin');
    txt.innerText = 'Syncing...';
    try {
      await fetch('/api/sync?force=true', { method: 'POST' });
      alert('Sinkronisasi berjalan di background!');
      setTimeout(async () => {
        await loadMetadata();
        await fetchVacancies();
      }, 3000);
    } catch (e) {
      alert('Gagal sync: ' + e.message);
    } finally {
      icon.classList.remove('animate-spin');
      txt.innerText = 'Sync';
    }
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
