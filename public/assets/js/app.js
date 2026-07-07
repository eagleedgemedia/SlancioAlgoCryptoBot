/* 
  Slancio Crypto Algo Treding Engine — Frontend JavaScript Logic
  =================================================
*/

const API_BASE = '/api';

// DOM Elements
const authView = document.getElementById('auth-view');
const dashboardView = document.getElementById('dashboard-view');
const botStatusText = document.getElementById('bot-status-text');
const botToggle = document.getElementById('bot-toggle');

// Helper: Toast Notifications
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = type === 'success' ? '<i class="fa-solid fa-circle-check text-accent"></i>' : '<i class="fa-solid fa-circle-exclamation text-danger"></i>';
    toast.innerHTML = `${icon} <span>${message}</span>`;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

// Helper: API Fetch with Auth Token
async function fetchAPI(endpoint, options = {}) {
    const token = localStorage.getItem('ksl_bot_token');
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token && !options.noAuth) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            headers
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            if (response.status === 401) {
                // Token expired or invalid
                handleLogout(false);
            }
            throw new Error(data.detail || 'An error occurred');
        }
        
        return data;
    } catch (error) {
        showToast(error.message, 'error');
        throw error;
    }
}

// ─── INIT ───
window.addEventListener('DOMContentLoaded', async () => {
    const token = localStorage.getItem('ksl_bot_token');
    if (token) {
        try {
            await loadUserProfile();
            showView('dashboard');
        } catch (e) {
            showView('auth');
        }
    } else {
        showView('auth');
    }
});

function showView(viewName) {
    if (viewName === 'auth') {
        authView.classList.add('active');
        dashboardView.classList.remove('active');
    } else {
        authView.classList.remove('active');
        dashboardView.classList.add('active');
    }
}

// ─── AUTHENTICATION ───
function switchAuthTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
    
    if (tab === 'login') {
        document.querySelector('.tab-btn:first-child').classList.add('active');
        document.getElementById('login-form').classList.add('active');
    } else {
        document.querySelector('.tab-btn:last-child').classList.add('active');
        document.getElementById('register-form').classList.add('active');
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
    
    const formData = new FormData();
    formData.append('username', document.getElementById('login-username').value);
    formData.append('password', document.getElementById('login-password').value);
    
    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if (!res.ok) throw new Error(data.detail || 'Login failed');
        
        localStorage.setItem('ksl_bot_token', data.access_token);
        showToast('Login successful!');
        
        await loadUserProfile();
        showView('dashboard');
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        btn.innerHTML = '<span>Access Dashboard</span> <i class="fa-solid fa-arrow-right"></i>';
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
    
    const payload = {
        username: document.getElementById('reg-username').value,
        email: document.getElementById('reg-email').value,
        password: document.getElementById('reg-password').value
    };
    
    try {
        await fetchAPI('/auth/register', {
            method: 'POST',
            body: JSON.stringify(payload),
            noAuth: true
        });
        
        showToast('Registration successful! Please login.');
        switchAuthTab('login');
        document.getElementById('login-username').value = payload.username;
    } catch (err) {
        // Handled by fetchAPI toast
    } finally {
        btn.innerHTML = '<span>Create Account</span> <i class="fa-solid fa-user-plus"></i>';
    }
}

function handleLogout(showMsg = true) {
    localStorage.removeItem('ksl_bot_token');
    showView('auth');
    if (showMsg) showToast('Logged out securely');
}

// ─── DASHBOARD LOGIC ───
async function loadUserProfile() {
    const user = await fetchAPI('/users/me');
    
    // Update UI
    document.getElementById('user-display-name').innerText = user.username;
    document.getElementById('user-role-badge').innerText = user.bot_enabled ? 'Active' : 'Paused';
    
    // Set Bot Toggle State
    botToggle.checked = user.bot_enabled;
    updateBotStatusUI(user.bot_enabled);
}

function updateBotStatusUI(isEnabled) {
    if (isEnabled) {
        botStatusText.innerText = 'ONLINE';
        botStatusText.style.color = 'var(--success)';
        botStatusText.style.textShadow = '0 0 10px var(--success-glow)';
    } else {
        botStatusText.innerText = 'OFFLINE';
        botStatusText.style.color = 'var(--text-muted)';
        botStatusText.style.textShadow = 'none';
    }
}

async function toggleBot(e) {
    const isEnabled = e.target.checked;
    try {
        const res = await fetchAPI('/users/bot/toggle', {
            method: 'POST',
            body: JSON.stringify({ enabled: isEnabled })
        });
        
        updateBotStatusUI(res.bot_enabled);
        document.getElementById('user-role-badge').innerText = res.bot_enabled ? 'Active' : 'Paused';
        showToast(res.bot_enabled ? 'Bot Engine Started 🚀' : 'Bot Engine Paused ⏸️');
    } catch (err) {
        // Revert UI switch on failure (e.g. no API keys saved)
        e.target.checked = !isEnabled;
        updateBotStatusUI(!isEnabled);
    }
}

async function saveApiKeys(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-save-keys');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Encrypting...';
    
    const payload = {
        api_key: document.getElementById('api-key-input').value,
        api_secret: document.getElementById('api-secret-input').value,
        exchange: 'delta_india'
    };
    
    try {
        const res = await fetchAPI('/users/keys', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        showToast(res.message);
        
        // Clear inputs for security
        document.getElementById('api-key-input').value = '';
        document.getElementById('api-secret-input').value = '';
        document.getElementById('api-secret-input').placeholder = '•••••••••••••••• (Saved)';
    } catch (err) {
        // Error handled in fetchAPI
    } finally {
        btn.innerHTML = originalText;
    }
}
