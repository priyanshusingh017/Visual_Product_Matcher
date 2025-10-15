// API Base URL - change for production
const API_URL = window.location.origin;

// State
let currentResults = [];
let uploadedImage = null;

// DOM Elements
const fileInput = document.getElementById('fileInput');
const urlInput = document.getElementById('urlInput');
const urlSearchBtn = document.getElementById('urlSearchBtn');
const uploadArea = document.getElementById('uploadArea');
const previewSection = document.getElementById('previewSection');
const previewImage = document.getElementById('previewImage');
const clearBtn = document.getElementById('clearBtn');
const loading = document.getElementById('loading');
const errorMessage = document.getElementById('errorMessage');
const errorText = document.getElementById('errorText');
const resultsSection = document.getElementById('resultsSection');
const productsGrid = document.getElementById('productsGrid');
const queryDescription = document.getElementById('queryDescription');
const categoryFilter = document.getElementById('categoryFilter');
const similarityFilter = document.getElementById('similarityFilter');
const similarityValue = document.getElementById('similarityValue');
const noResults = document.getElementById('noResults');
const tabButtons = document.querySelectorAll('.tab-button');
const tabContents = document.querySelectorAll('.tab-content');
const themeToggle = document.getElementById('themeToggle');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadCategories();
    initTheme();
});

// Setup Event Listeners
function setupEventListeners() {
    // Tab switching (mouse + keyboard)
    tabButtons.forEach(button => {
        button.addEventListener('click', () => switchTab(button.dataset.tab));
        button.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                switchTab(button.dataset.tab);
            }
        });
    });

    // File upload
    uploadArea.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInput.click();
        }
    });
    fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);

    // URL search
    urlSearchBtn.addEventListener('click', handleUrlSearch);
    urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleUrlSearch();
    });

    // Clear button
    clearBtn.addEventListener('click', clearUpload);

    // Theme toggle
    if (themeToggle) {
        themeToggle.addEventListener('click', toggleTheme);
    }

    // Filters
    categoryFilter.addEventListener('change', applyFilters);
    const debouncedApply = debounce(applyFilters, 120);
    similarityFilter.addEventListener('input', (e) => {
        similarityValue.textContent = `${e.target.value}%`;
        debouncedApply();
    });
}

// Tab Switching
function switchTab(tabName) {
    tabButtons.forEach(btn => {
        btn.classList.remove('active');
        btn.setAttribute('aria-selected', 'false');
    });
    tabContents.forEach(content => {
        content.classList.remove('active');
        content.setAttribute('aria-hidden', 'true');
    });

    const activeButton = document.querySelector(`[data-tab="${tabName}"]`);
    const activePanel = document.getElementById(`${tabName}-tab`);
    if (activeButton && activePanel) {
        activeButton.classList.add('active');
        activeButton.setAttribute('aria-selected', 'true');
        activePanel.classList.add('active');
        activePanel.setAttribute('aria-hidden', 'false');
        activeButton.focus({ preventScroll: true });
    }

    clearUpload();
}

// File Upload Handlers
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        uploadedImage = file;
        displayPreview(file);
        searchByImage(file);
    }
}

function handleDragOver(e) {
    e.preventDefault();
    uploadArea.classList.add('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');

    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) {
        uploadedImage = file;
        fileInput.files = e.dataTransfer.files;
        displayPreview(file);
        searchByImage(file);
    } else {
        showError('Please drop a valid image file');
    }
}

// URL Search Handler
async function handleUrlSearch() {
    const url = urlInput.value.trim();

    if (!url) {
        showError('Please enter an image URL');
        return;
    }

    if (!isValidUrl(url)) {
        showError('Please enter a valid URL');
        return;
    }

    uploadedImage = url;
    previewImage.src = url;
    previewSection.style.display = 'block';

    await searchByUrl(url);
}

// Display Preview
function displayPreview(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImage.src = e.target.result;
        previewSection.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

// Clear Upload
function clearUpload() {
    uploadedImage = null;
    fileInput.value = '';
    urlInput.value = '';
    previewSection.style.display = 'none';
    resultsSection.style.display = 'none';
    hideError();
}

// Search by Image File
async function searchByImage(file) {
    showLoading();
    hideError();

    const formData = new FormData();
    formData.append('image', file);

    try {
        const response = await fetch(`${API_URL}/api/search`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Search failed');
        }

        const data = await response.json();
        displayResults(data);
    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
}

// Search by URL
async function searchByUrl(url) {
    showLoading();
    hideError();

    try {
        const response = await fetch(`${API_URL}/api/search`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ image_url: url })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Search failed');
        }

        const data = await response.json();
        displayResults(data);
    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
}

// Display Results
function displayResults(data) {
    currentResults = data.results || [];

    // Helpers for display
    const pill = (t) => `<span class="pill">${escapeHtml(String(t))}</span>`;
    const row = (label, arr) => Array.isArray(arr) && arr.length ? `
        <div class="analysis-row"><span class="label">${label}</span>
        <div class="values">${arr.map(pill).join('')}</div></div>
    ` : '';

    // Normalize analysis object:
    // - Backends may return a structured object in `analysis`
    // - Older/fallback may return JSON-ish string in `query_description` (even wrapped in ```json fences)
    let analysis = null;
    if (data.analysis && typeof data.analysis === 'object') {
        analysis = data.analysis;
    } else if (typeof data.analysis === 'string' && looksLikeJson(data.analysis)) {
        analysis = tryParseJsonLoose(extractJsonObject(data.analysis));
    }

    if (analysis && typeof analysis === 'object') {
        const a = analysis;
        const ensureArray = (v) => Array.isArray(v) ? v : (v ? [v] : []);
        const categoryPill = a.category ? pill(a.category) : '<span class="pill">Unknown</span>';
        queryDescription.innerHTML = `
            <div class="analysis">
                <div class="summary"><strong>Image Analysis:</strong> ${escapeHtml(formatAnalysisProse({
                    summary: a.summary,
                    category: a.category,
                    colors: ensureArray(a.colors),
                    materials: ensureArray(a.materials),
                    style: ensureArray(a.style),
                    objects: ensureArray(a.objects),
                    suggested_tags: ensureArray(a.suggested_tags)
                }))}</div>
                <div class="analysis-row"><span class="label">Category</span><div class="values">${categoryPill}</div></div>
                ${row('Colors', ensureArray(a.colors))}
                ${row('Materials', ensureArray(a.materials))}
                ${row('Style', ensureArray(a.style))}
                ${row('Objects', ensureArray(a.objects))}
                ${row('Tags', ensureArray(a.suggested_tags))}
            </div>
        `;
    } else {
        // If no structured analysis available, show a minimal message
        queryDescription.innerHTML = '<strong>Image Analysis:</strong> Analysis unavailable.';
    }

    resultsSection.style.display = 'block';
    applyFilters();
}

// Detect if a string contains JSON or JSON-like object
function looksLikeJson(text) {
    if (typeof text !== 'string') return false;
    const t = stripCodeFences(text).trim();
    return (t.startsWith('{') && t.endsWith('}')) || (t.startsWith('[') && t.endsWith(']'));
}

// Extract the probable JSON object from a string that may include ```json fences or prefixes
function extractJsonObject(text) {
    if (typeof text !== 'string') return text;
    let t = stripCodeFences(text);
    // Try to find first { ... } block
    const start = t.indexOf('{');
    const end = t.lastIndexOf('}');
    if (start !== -1 && end !== -1 && end > start) {
        return t.slice(start, end + 1);
    }
    return t;
}

// Try to parse JSON but also handle loose JSON with single quotes and trailing commas
function tryParseJsonLoose(text) {
    if (typeof text !== 'string') return null;
    try {
        return JSON.parse(text);
    } catch (_) {
        try {
            // Replace single quotes with double quotes (naive but effective for simple cases)
            let s = text
                .replace(/\r?\n/g, ' ')
                .replace(/(')(?:(?=(\\?))\2.)*?'/g, (m) => '"' + m.slice(1, -1).replace(/\\"/g, '"').replace(/"/g, '\\"') + '"')
                .replace(/,\s*([}\]])/g, '$1'); // remove trailing commas
            return JSON.parse(s);
        } catch (__) {
            return null;
        }
    }
}

function stripCodeFences(text) {
    if (typeof text !== 'string') return '';
    // Remove ```json ... ``` or ``` ... ``` fences
    return text
        .replace(/```json/gi, '')
        .replace(/```/g, '')
        .trim();
}

// Build a professional, human-friendly paragraph from analysis fields
function formatAnalysisProse(a) {
    const sentences = [];

    const uniq = (arr) => Array.from(new Map((arr || []).filter(Boolean).map(v => [v.toLowerCase().trim(), v.trim()])).values());
    const joinNatural = (arr) => {
        const list = uniq(arr);
        if (list.length === 0) return '';
        if (list.length === 1) return list[0];
        if (list.length === 2) return `${list[0]} and ${list[1]}`;
        return `${list.slice(0, -1).join(', ')}, and ${list[list.length - 1]}`;
    };

    // Prefer model-provided summary if it's present
    const baseSummary = (a.summary || '').toString().trim();
    if (baseSummary) {
        sentences.push(baseSummary.replace(/^[-•\s]+/, ''));
    } else {
        const objectsText = joinNatural(a.objects);
        if (objectsText) {
            sentences.push(`The image shows ${objectsText}.`);
        } else {
            sentences.push('The image shows a product scene.');
        }
    }

    if (a.category) {
        sentences.push(`It falls under the ${a.category} category.`);
    }

    const colorsText = joinNatural(a.colors);
    if (colorsText) sentences.push(`Dominant colors include ${colorsText}.`);

    const materialsText = joinNatural(a.materials);
    if (materialsText) sentences.push(`Materials appear to include ${materialsText}.`);

    const styleText = joinNatural(a.style);
    if (styleText) sentences.push(`Style cues are ${styleText}.`);

    // Optionally add tags if they add new information beyond objects/style
    const tags = uniq(a.suggested_tags || []);
    const tagsText = joinNatural(tags.slice(0, 6));
    if (tagsText) sentences.push(`Related tags: ${tagsText}.`);

    return sentences.join(' ');
}

// Apply Filters
function applyFilters() {
    const selectedCategory = categoryFilter.value;
    const minSimilarity = parseFloat(similarityFilter.value) / 100;

    let filtered = currentResults.filter(item => {
        const matchesCategory = !selectedCategory || item.product.category === selectedCategory;
        const matchesSimilarity = item.similarity >= minSimilarity;
        return matchesCategory && matchesSimilarity;
    });

    if (filtered.length === 0) {
        productsGrid.innerHTML = '';
        noResults.style.display = 'block';
        return;
    }

    noResults.style.display = 'none';
    renderProducts(filtered);
}

// Render Products
function renderProducts(products) {
    productsGrid.innerHTML = products.map(item => createProductCard(item)).join('');
}

// Create Product Card
function createProductCard(item) {
    const { product, similarity } = item;
    const similarityPercent = Math.round(similarity * 100);

    return `
        <a class="product-card" href="${product.image_url}" target="_blank" rel="noopener noreferrer" aria-label="Open image for ${escapeHtml(product.name)} in a new tab">
            <img src="${product.image_url}" alt="${escapeHtml(product.name)}" class="product-image" loading="lazy"
                 onerror="this.src='https://via.placeholder.com/250x200?text=Image+Not+Available'">
            <div class="product-info">
                <h3 class="product-name">${escapeHtml(product.name)}</h3>
                <span class="product-category">${escapeHtml(product.category)}</span>
                <div class="product-price">$${product.price.toFixed(2)}</div>
                <p class="product-description">${escapeHtml(product.description)}</p>
                <div class="product-similarity" aria-label="Similarity ${similarityPercent} percent">
                    <div class="similarity-bar" aria-hidden="true">
                        <div class="similarity-fill" style="width: ${similarityPercent}%"></div>
                    </div>
                    <span class="similarity-score">${similarityPercent}%</span>
                </div>
            </div>
        </a>
    `;
}

// Simple debounce helper
function debounce(fn, delay = 150) {
    let t;
    return function(...args) {
        clearTimeout(t);
        t = setTimeout(() => fn.apply(this, args), delay);
    };
}

// Load Categories
async function loadCategories() {
    try {
        const response = await fetch(`${API_URL}/api/categories`);
        const data = await response.json();

        data.categories.forEach(category => {
            const option = document.createElement('option');
            option.value = category;
            option.textContent = category;
            categoryFilter.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load categories:', error);
    }
}

// Utility Functions
function showLoading() {
    loading.style.display = 'block';
    resultsSection.style.display = 'none';
    loading.setAttribute('aria-busy', 'true');
}

function hideLoading() {
    loading.style.display = 'none';
    loading.setAttribute('aria-busy', 'false');
}

function showError(message) {
    errorText.textContent = message;
    errorMessage.style.display = 'flex';
    errorMessage.setAttribute('aria-hidden', 'false');
}

function hideError() {
    errorMessage.style.display = 'none';
    errorMessage.setAttribute('aria-hidden', 'true');
}

// Theme handling
function initTheme() {
    const stored = localStorage.getItem('vpm-theme');
    if (stored) {
        document.documentElement.setAttribute('data-theme', stored);
        updateThemeToggle(stored);
        return;
    }
    // Prefer user OS setting
    const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
    const theme = prefersLight ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeToggle(theme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('vpm-theme', next);
    updateThemeToggle(next);
}

function updateThemeToggle(theme) {
    if (!themeToggle) return;
    const isDark = theme !== 'light';
    themeToggle.setAttribute('aria-pressed', String(isDark));
    themeToggle.textContent = isDark ? 'Light theme' : 'Dark theme';
}

function isValidUrl(string) {
    try {
        const url = new URL(string);
        return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (_) {
        return false;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
