/* 
  Slancio Crypto Algo Treding Engine — Full App JavaScript
*/

const API_BASE = '/api';
let _currentOTPContext = null; // { identifier, otp_type, onSuccess }
let _currentUser = null;

// ─── TOAST ───
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = type === 'success' ? '<i class="fa-solid fa-circle-check text-accent"></i>' : '<i class="fa-solid fa-circle-exclamation text-danger"></i>';
    toast.innerHTML = `${icon} <span>${message}</span>`;
    container.appendChild(toast);
    setTimeout(() => { toast.classList.add('fade-out'); setTimeout(() => toast.remove(), 400); }, 4000);
}

// ─── API FETCH ───
async function fetchAPI(endpoint, options = {}) {
    const token = localStorage.getItem('ksl_bot_token');
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (token && !options.noAuth) headers['Authorization'] = `Bearer ${token}`;
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
        const data = await response.json();
        if (!response.ok) {
            if (response.status === 401) handleLogout(false);
            throw new Error(data.detail || 'An error occurred');
        }
        return data;
    } catch (error) {
        if (!options.headers || !options.headers['x-silent-error']) {
            showToast(error.message, 'error');
        }
        throw error;
    }
}

// ─── INIT ───
window.addEventListener('DOMContentLoaded', async () => {
    const token = localStorage.getItem('ksl_bot_token');
    if (token) {
        try { await loadUserProfile(); showView('dashboard'); }
        catch (e) { showView('auth'); }
    } else { showView('auth'); }
});

function showView(viewName) {
    document.getElementById('auth-view').classList.toggle('active', viewName === 'auth');
    document.getElementById('dashboard-view').classList.toggle('active', viewName === 'dashboard');
}

// ─── MULTI-PAGE NAVIGATION ───
function showPage(pageName, navEl) {
    document.querySelectorAll('.page-content').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById(`page-${pageName}`).classList.add('active');
    if (navEl) navEl.classList.add('active');

    if (pageName === 'trades') loadTradeHistory();
    if (pageName === 'admin') loadAdminData();
}

// ─── AUTH TAB ───
function switchAuthTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.auth-form').forEach(f => f.classList.remove('active'));
    const tabIndex = { login: 0, register: 1, forgot: 2 };
    document.querySelectorAll('.tab-btn')[tabIndex[tab]].classList.add('active');
    document.getElementById(`${tab}-form`).classList.add('active');
}

// ─── THEME MANAGEMENT ───
const themes = ['night', 'day', 'bluelight'];
let currentTheme = localStorage.getItem('ksl_theme') || 'night';

function applyTheme(theme) {
    document.body.classList.remove('theme-day', 'theme-bluelight');
    if (theme !== 'night') {
        document.body.classList.add(`theme-${theme}`);
    }
    
    // Update icons
    const iconClass = theme === 'day' ? 'fa-sun text-orange' 
                    : theme === 'bluelight' ? 'fa-eye-low-vision text-orange' 
                    : 'fa-moon';
                    
    document.getElementById('theme-toggle-auth').innerHTML = `<i class="fa-solid ${iconClass}"></i>`;
    document.getElementById('theme-toggle-dash').innerHTML = `<i class="fa-solid ${iconClass}"></i>`;
}

function cycleTheme() {
    let idx = themes.indexOf(currentTheme);
    idx = (idx + 1) % themes.length;
    currentTheme = themes[idx];
    localStorage.setItem('ksl_theme', currentTheme);
    applyTheme(currentTheme);
    showToast(`Theme changed to ${currentTheme.toUpperCase()}`);
}

// Apply on load
applyTheme(currentTheme);


// ─── LOGIN ───
async function handleLogin(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
    const formData = new FormData();
    formData.append('username', document.getElementById('login-username').value);
    formData.append('password', document.getElementById('login-password').value);
    try {
        const res = await fetch(`${API_BASE}/auth/login`, { method: 'POST', body: formData });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Login failed');
        localStorage.setItem('ksl_bot_token', data.access_token);
        showToast('Login successful!');
        await loadUserProfile();
        showView('dashboard');
    } catch (err) { showToast(err.message, 'error'); }
    finally { btn.innerHTML = '<span>Access Dashboard</span> <i class="fa-solid fa-arrow-right"></i>'; }
}

// ─── REGISTER ───
async function handleRegister(e) {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
    const payload = {
        username: document.getElementById('reg-username').value,
        email: document.getElementById('reg-email').value,
        mobile_number: document.getElementById('reg-mobile').value,
        password: document.getElementById('reg-password').value
    };
    try {
        const res = await fetchAPI('/auth/register', { method: 'POST', body: JSON.stringify(payload), noAuth: true });
        
        // Registration now auto-verifies — no OTP needed, go straight to login
        showToast(`Account created! You are now ${res.role}. Please login.`, 'success');
        switchAuthTab('login');
        document.getElementById('login-username').value = payload.username;
    } catch (err) { /* handled */ }
    finally { btn.innerHTML = '<span>Create Account</span> <i class="fa-solid fa-user-plus"></i>'; }
}

// ─── FORGOT PASSWORD ───
let _resetContext = null;

async function handleForgotPassword(e) {
    e.preventDefault();
    const identifier = document.getElementById('forgot-identifier').value.trim();
    const btn = e.target.querySelector('button');
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
    try {
        await fetchAPI('/auth/forgot-password', {
            method: 'POST',
            body: JSON.stringify({ identifier, otp_type: 'forgot_password' }),
            noAuth: true
        });
        showToast(`OTP sent to ${identifier}`);
        showOTPModal(identifier, 'forgot_password', (otp) => {
            // After OTP verified, show custom Reset Password Modal instead of ugly prompt
            _resetContext = { identifier, otp };
            document.getElementById('new-password-input').value = '';
            document.getElementById('reset-password-modal').style.display = 'flex';
        }, true); // true = return raw OTP to callback
    } catch (err) { /* handled */ }
    finally { btn.innerHTML = '<span>Send OTP</span> <i class="fa-solid fa-paper-plane"></i>'; }
}

function closeResetPasswordModal() {
    document.getElementById('reset-password-modal').style.display = 'none';
    _resetContext = null;
}

async function submitNewPassword(e) {
    e.preventDefault();
    if (!_resetContext) return;
    
    const newPwd = document.getElementById('new-password-input').value;
    if (newPwd.length < 8) { showToast('Password must be at least 8 characters.', 'error'); return; }
    
    const { identifier, otp } = _resetContext;
    
    try {
        await fetchAPI('/auth/reset-password', {
            method: 'POST',
            body: JSON.stringify({ identifier, otp_code: otp, new_password: newPwd }),
            noAuth: true
        });
        showToast('Password reset! Please login.', 'success');
        closeResetPasswordModal();
        switchAuthTab('login');
        document.getElementById('login-username').value = identifier;
    } catch(err) { /* Toast already handled by fetchAPI */ }
}

// ─── OTP MODAL ───
function showOTPModal(identifier, otp_type, onSuccess, returnOTP = false) {
    _currentOTPContext = { identifier, otp_type, onSuccess, returnOTP };
    const subtitles = {
        email_verify: `Enter OTP sent to ${identifier}`,
        mobile_verify: `Enter OTP sent to +91${identifier}`,
        forgot_password: `Enter password reset OTP sent to ${identifier}`,
    };
    document.getElementById('otp-modal-subtitle').innerText = subtitles[otp_type] || 'Enter OTP';
    ['otp-d1','otp-d2','otp-d3','otp-d4','otp-d5','otp-d6'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('otp-modal').style.display = 'flex';
    document.getElementById('otp-d1').focus();
}

function closeOTPModal() {
    document.getElementById('otp-modal').style.display = 'none';
    _currentOTPContext = null;
}

function otpInput(el, nextId) {
    if (el.value.length === 1 && nextId) document.getElementById(nextId).focus();
}

async function submitOTP() {
    if (!_currentOTPContext) return;
    const otp = ['otp-d1','otp-d2','otp-d3','otp-d4','otp-d5','otp-d6'].map(id => document.getElementById(id).value).join('');
    if (otp.length < 6) { showToast('Enter all 6 digits.', 'error'); return; }

    const btn = document.getElementById('otp-submit-btn');
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Verifying...';
    
    try {
        if (_currentOTPContext.otp_type !== 'forgot_password') {
            await fetchAPI('/auth/otp/verify', {
                method: 'POST',
                body: JSON.stringify({ identifier: _currentOTPContext.identifier, otp_code: otp, otp_type: _currentOTPContext.otp_type }),
                noAuth: true
            });
        }
        closeOTPModal();
        if (_currentOTPContext) {
            if (_currentOTPContext.returnOTP) _currentOTPContext.onSuccess(otp);
            else _currentOTPContext.onSuccess();
        }
    } catch (err) { /* toast shown by fetchAPI */ }
    finally { btn.innerHTML = '<i class="fa-solid fa-check-circle"></i> Verify OTP'; }
}

async function resendOTP() {
    if (!_currentOTPContext) return;
    await fetchAPI('/auth/otp/send', {
        method: 'POST',
        body: JSON.stringify({ identifier: _currentOTPContext.identifier, otp_type: _currentOTPContext.otp_type }),
        noAuth: true
    });
    showToast('OTP resent!');
}

// ─── LOGOUT ───
function handleLogout(showMsg = true) {
    localStorage.removeItem('ksl_bot_token');
    _currentUser = null;
    showView('auth');
    if (showMsg) showToast('Logged out securely');
}

// ─── PROFILE ───
async function loadUserProfile() {
    const user = await fetchAPI('/users/me');
    _currentUser = user;
    document.getElementById('user-display-name').innerText = user.username;
    document.getElementById('user-role-badge').innerText = user.role === 'admin' ? '👑 Admin' : (user.bot_enabled ? 'Active' : 'Paused');
    botToggle.checked = user.bot_enabled;
    updateBotStatusUI(user.bot_enabled);



    // Show admin nav link
    if (user.role === 'admin') document.getElementById('admin-nav-link').style.display = 'flex';

    // Show verification status in settings page
    document.getElementById('email-display').innerText = user.email || '—';
    document.getElementById('mobile-display').innerText = user.mobile_number ? `+91${user.mobile_number}` : '—';
    document.getElementById('email-verify-status').innerHTML = user.is_email_verified
        ? '<span class="badge badge-green"><i class="fa-solid fa-check"></i> Verified</span>'
        : '<button class="btn btn-sm btn-ghost" onclick="triggerVerification(\'email\')">Verify Now</button>';
    document.getElementById('mobile-verify-status').innerHTML = user.is_mobile_verified
        ? '<span class="badge badge-green"><i class="fa-solid fa-check"></i> Verified</span>'
        : '<button class="btn btn-sm btn-ghost" onclick="triggerVerification(\'mobile\')">Verify Now</button>';

    loadStats();
}

async function triggerVerification(type) {
    if (!_currentUser) return;
    const identifier = type === 'email' ? _currentUser.email : _currentUser.mobile_number;
    const otp_type = type === 'email' ? 'email_verify' : 'mobile_verify';
    await fetchAPI('/auth/otp/send', {
        method: 'POST',
        body: JSON.stringify({ identifier, otp_type }),
        noAuth: false
    });
    showOTPModal(identifier, otp_type, () => {
        showToast(`${type === 'email' ? 'Email' : 'Mobile'} verified!`);
        loadUserProfile();
    });
}

// ─── BOT TOGGLE ───
const botToggle = document.getElementById('bot-toggle');
function updateBotStatusUI(isEnabled) {
    const txt = document.getElementById('bot-status-text');
    txt.innerText = isEnabled ? 'ONLINE' : 'OFFLINE';
    txt.style.color = isEnabled ? 'var(--success)' : 'var(--text-muted)';
    txt.style.textShadow = isEnabled ? '0 0 10px var(--success-glow)' : 'none';
}
async function toggleBot(e) {
    const isEnabled = e.target.checked;
    try {
        const res = await fetchAPI('/users/bot/toggle', { method: 'POST', body: JSON.stringify({ enabled: isEnabled }) });
        updateBotStatusUI(res.bot_enabled);
        document.getElementById('user-role-badge').innerText = res.bot_enabled ? 'Active' : 'Paused';
        showToast(res.bot_enabled ? 'Bot Engine Started 🚀' : 'Bot Engine Paused ⏸️');
    } catch (err) {
        e.target.checked = !isEnabled;
        updateBotStatusUI(!isEnabled);
    }
}

// ─── API KEYS ───
async function loadApiKeys() {
    try {
        const keys = await fetchAPI('/users/keys');
        const container = document.getElementById('api-keys-list');
        container.innerHTML = '';
        
        if (keys.length === 0) {
            container.innerHTML = '<div class="text-muted text-center py-2">No API keys saved yet.</div>';
            return;
        }
        
        keys.forEach(k => {
            const div = document.createElement('div');
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.justifyContent = 'space-between';
            div.style.padding = '10px';
            div.style.border = '1px solid var(--panel-border)';
            div.style.borderRadius = '8px';
            div.style.marginBottom = '8px';
            div.style.background = k.is_selected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(0,0,0,0.2)';
            
            div.innerHTML = `
                <div>
                    <strong>${k.api_name}</strong>
                    <span class="badge ${k.is_selected ? 'badge-green' : 'badge-outline'} ms-2">${k.is_selected ? 'Active' : 'Standby'}</span>
                </div>
                <div style="display: flex; gap: 15px; align-items: center;">
                    <div id="margin-${k.id}" class="text-green" style="font-weight: 600; font-size: 0.95rem; background: rgba(16, 185, 129, 0.1); padding: 4px 10px; border-radius: 6px;"><i class="fa-solid fa-circle-notch fa-spin"></i></div>
                    <div style="display: flex; gap: 5px;">
                        <button class="btn btn-sm ${k.is_selected ? 'btn-green' : 'btn-ghost'}" onclick="selectApiKey('${k.id}')" title="Toggle API">
                            ${k.is_selected ? 'ON' : 'OFF'}
                        </button>
                        <button class="btn btn-sm btn-danger-outline" onclick="deleteApiKey('${k.id}')" title="Delete"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </div>
            `;
            container.appendChild(div);
            
            // Fetch margin asynchronously for this key
            fetchAPI(`/users/keys/${k.id}/balance`, { headers: { 'x-silent-error': 'true' } }).then(res => {
                if (res.status === 'error') {
                    document.getElementById(`margin-${k.id}`).innerHTML = '<span class="text-danger" style="font-size: 0.8rem;">Invalid Key</span>';
                } else {
                    if (res.margin_inr !== undefined) {
                        document.getElementById(`margin-${k.id}`).innerHTML = `₹${res.margin_inr.toFixed(2)} <span style="font-size: 0.7em; color: var(--text-muted);">($${res.margin_usdt.toFixed(2)})</span>`;
                    } else {
                        document.getElementById(`margin-${k.id}`).innerText = `$0.00`;
                    }
                }
            }).catch(e => {
                const el = document.getElementById(`margin-${k.id}`);
                if (el) el.innerHTML = '<span class="text-danger" style="font-size: 0.8rem;">Error</span>';
            });
        });
    } catch(e) {}
}

async function selectApiKey(id) {
    try {
        await fetchAPI(`/users/keys/${id}/select`, { method: 'POST' });
        showToast('Active API key updated.');
        loadApiKeys();
    } catch(e) {}
}

async function deleteApiKey(id) {
    if(!confirm('Are you sure you want to delete this API Key?')) return;
    try {
        await fetchAPI(`/users/keys/${id}`, { method: 'DELETE' });
        showToast('API key deleted.');
        loadApiKeys();
    } catch(e) {}
}

async function saveApiKeys(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-save-keys');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Adding...';
    const payload = { 
        api_name: document.getElementById('api-name-input').value,
        api_key: document.getElementById('api-key-input').value, 
        api_secret: document.getElementById('api-secret-input').value, 
        exchange: 'delta_india' 
    };
    try {
        const res = await fetchAPI('/users/keys', { method: 'POST', body: JSON.stringify(payload) });
        showToast(res.message);
        document.getElementById('api-name-input').value = '';
        document.getElementById('api-key-input').value = '';
        document.getElementById('api-secret-input').value = '';
        loadApiKeys();
    } catch (err) { /* handled */ }
    finally { btn.innerHTML = orig; }
}



// ─── STATS ───
async function loadStats() {
    try {
        const stats = await fetchAPI('/users/stats');
        document.getElementById('stat-winrate').innerText = `${stats.win_rate}%`;
        document.getElementById('stat-pnl').innerText = `$${stats.total_pnl.toFixed(2)}`;
        document.getElementById('stat-pnl').className = stats.total_pnl < 0 ? 'text-danger' : 'text-gradient';
        document.getElementById('stat-trades').innerText = stats.total_trades;
    } catch(e) {}
    
    // Also load active trade for the dashboard
    loadActiveTrade();
}

async function loadActiveTrade() {
    try {
        const trades = await fetchAPI('/users/trades');
        const activeTrade = trades.find(t => t.status === 'OPEN' || t.status === 'open');
        const card = document.getElementById('active-trade-card');
        
        if (activeTrade) {
            document.getElementById('active-trade-pair').innerText = activeTrade.symbol;
            document.getElementById('active-trade-type').innerText = activeTrade.side.toUpperCase();
            document.getElementById('active-trade-type').className = (activeTrade.side === 'buy' || activeTrade.side === 'long') ? 'text-green' : 'text-danger';
            document.getElementById('active-trade-entry').innerText = `$${activeTrade.entry_price.toFixed(2)}`;
            document.getElementById('active-trade-target').innerText = activeTrade.pnl_usdt != null ? `$${activeTrade.pnl_usdt.toFixed(2)}` : 'Tracking...';
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    } catch (e) {
        document.getElementById('active-trade-card').style.display = 'none';
    }
}

// ─── TRADE HISTORY ───
async function loadTradeHistory() {
    try {
        const trades = await fetchAPI('/users/trades');
        const tbody = document.getElementById('trades-tbody');
        if (!trades || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No trades found. Bot must be ON to generate trades.</td></tr>';
            return;
        }
        tbody.innerHTML = '';
        trades.forEach(t => {
            const row = document.createElement('tr');
            const sideClass = t.side === 'buy' || t.side === 'long' ? 'text-green' : 'text-danger';
            const statusBadge = t.status === 'closed' ? '<span class="badge badge-outline">Closed</span>' : '<span class="badge badge-green">Open</span>';
            const pnlStr = t.pnl_usdt != null ? `$${t.pnl_usdt.toFixed(2)}` : '-';
            const pnlClass = t.pnl_usdt > 0 ? 'text-green' : (t.pnl_usdt < 0 ? 'text-danger' : '');
            const openedAt = t.opened_at ? new Date(t.opened_at).toLocaleString('en-IN') : '-';
            row.innerHTML = `
                <td><strong>${t.symbol}</strong></td>
                <td class="${sideClass}">${t.side.toUpperCase()}</td>
                <td>$${t.entry_price.toFixed(2)}</td>
                <td>${t.exit_price ? '$'+t.exit_price.toFixed(2) : '-'}</td>
                <td>${statusBadge}</td>
                <td class="${pnlClass}"><strong>${pnlStr}</strong></td>
                <td class="text-muted">${openedAt}</td>
            `;
            tbody.appendChild(row);
        });
    } catch(e) { console.error("Trade history load failed:", e); }
}

// ─── ADMIN PANEL ───
async function loadAdminData() {
    if (!_currentUser || _currentUser.role !== 'admin') return;
    try {
        const stats = await fetchAPI('/admin/stats');
        document.getElementById('admin-stat-users').innerText = stats.total_users;
        document.getElementById('admin-stat-open').innerText = stats.open_trades || 0;
        document.getElementById('admin-stat-pnl').innerText = `$${(stats.system_total_pnl || 0).toFixed(2)}`;
    } catch(e) {}

    await loadAdminOpenTrades();
    await loadAdminUsers();
    await loadApiKeys();
}

async function loadAdminOpenTrades() {
    try {
        const trades = await fetchAPI('/admin/trades/open');
        const tbody = document.getElementById('admin-trades-tbody');
        if (!trades || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center text-muted py-3">No open trades right now.</td></tr>';
            return;
        }
        tbody.innerHTML = '';
        trades.forEach(t => {
            const row = document.createElement('tr');
            const sideClass = t.side === 'buy' || t.side === 'long' ? 'text-green' : 'text-danger';
            const openedAt = t.opened_at ? new Date(t.opened_at).toLocaleString('en-IN') : '-';
            row.innerHTML = `
                <td><strong>${t.username}</strong></td>
                <td>${t.symbol}</td>
                <td class="${sideClass}"><strong>${t.side.toUpperCase()}</strong></td>
                <td>$${t.entry_price.toFixed(2)}</td>
                <td class="text-danger">$${t.stop_loss.toFixed(2)}</td>
                <td class="text-green">$${t.take_profit_target.toFixed(2)}</td>
                <td>${t.quantity}</td>
                <td>${t.leverage}x</td>
                <td class="text-muted">${openedAt}</td>
                <td>
                    <button class="btn btn-sm btn-ghost" title="Modify SL/TP"
                        onclick="adminModifyTrade('${t.id}', ${t.stop_loss}, ${t.take_profit_target})">
                        <i class="fa-solid fa-pen-to-square"></i>
                    </button>
                    <button class="btn btn-sm btn-danger-outline" title="Force Close Position"
                        onclick="adminCloseTrade('${t.id}', '${t.username}', '${t.symbol}')">
                        <i class="fa-solid fa-xmark"></i> Close
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch(e) { console.error("Admin open trades failed:", e); }
}

async function loadAdminUsers() {
    try {
        const users = await fetchAPI('/admin/users');
        const tbody = document.getElementById('admin-users-tbody');
        tbody.innerHTML = '';
        users.forEach(u => {
            const row = document.createElement('tr');
            const pct = ((u.position_size_pct || 0.02) * 100).toFixed(1);
            const lev = u.max_leverage || 10;
            const tf = u.trading_timeframe || '1h';
            const margin = u.margin_type || 'isolated';
            const sl = u.stop_loss_points || 600;
            const tp = u.take_profit_points || 800;
            const entryDist = u.ema_distance_points ?? 400;
            row.innerHTML = `
                <td><strong>${u.username}</strong></td>
                <td class="text-muted">${u.email}</td>
                <td><span class="badge ${u.role === 'admin' ? 'badge-green' : 'badge-outline'}">${u.role}</span></td>
                <td>${u.is_email_verified ? '✅' : '❌'}</td>
                <td><span class="badge ${u.bot_enabled ? 'badge-green' : 'badge-outline'}">${u.bot_enabled ? 'ON' : 'OFF'}</span></td>
                <td><code>${tf}</code></td>
                <td><strong>${lev}x</strong></td>
                <td>${sl}</td>
                <td>${tp}</td>
                <td><strong>${entryDist}</strong></td>
                    <button class="btn btn-sm btn-ghost" title="Edit Trading Config"
                        onclick="adminEditConfig('${u.id}','${u.username}',${pct},${lev},'${tf}',${sl},${tp},${entryDist})">
                        <i class="fa-solid fa-sliders"></i> Edit
                    </button>
                    ${u.role !== 'admin' ? `
                    <button class="btn btn-sm btn-danger-outline" title="${u.is_active ? 'Disable User' : 'Enable User'}"
                        onclick="adminToggleUser('${u.id}')">
                        ${u.is_active ? '<i class="fa-solid fa-ban"></i>' : '<i class="fa-solid fa-check"></i>'}
                    </button>
                    ` : ''}
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch(e) { console.error("Admin users load failed:", e); }
}

async function adminToggleUser(userId) {
    try {
        await fetchAPI(`/admin/users/${userId}/toggle-active`, { method: 'POST' });
        showToast('User status updated.');
        loadAdminUsers();
    } catch(e) {}
}

async function adminModifyTrade(tradeId, currentSL, currentTP) {
    const sl = prompt(`New Stop Loss price [current: $${currentSL.toFixed(2)}]:`, currentSL.toFixed(2));
    if (!sl) return;
    const tp = prompt(`New Take Profit price [current: $${currentTP.toFixed(2)}]:`, currentTP.toFixed(2));
    if (!tp) return;

    try {
        const resp = await fetchAPI(`/admin/trades/${tradeId}/modify`, {
            method: 'PUT',
            body: JSON.stringify({ stop_loss: parseFloat(sl), take_profit: parseFloat(tp) })
        });
        showToast(`SL/TP modified — ${resp.delta_exchange_status}`);
        loadAdminData();
    } catch(e) {}
}

async function adminCloseTrade(tradeId, username, symbol) {
    if (!confirm(`Force-close ${symbol} trade for user "${username}" at market price? This cannot be undone.`)) return;
    try {
        const resp = await fetchAPI(`/admin/trades/${tradeId}/close`, { method: 'POST' });
        const pnl = resp.pnl_usdt != null ? ` | PnL: $${resp.pnl_usdt.toFixed(2)}` : '';
        showToast(`Position closed${pnl} — ${resp.delta_exchange_status}`);
        loadAdminData();
    } catch(e) {}
}

async function adminEditConfig(userId, username, curPct, curLev, curTf, curSL, curTP, curEntryDist) {
    document.getElementById('ac-userid').value = userId;
    document.getElementById('ac-pct').value = curPct;
    document.getElementById('admin-config-subtitle').innerText = `Modify trading parameters for ${username}`;
    
    document.getElementById('ac-tf').value = curTf;
    
    const levSelect = document.getElementById('ac-lev');
    if (![...levSelect.options].some(o => o.value == curLev)) {
        const opt = document.createElement('option');
        opt.value = curLev;
        opt.text = `${curLev}x (Current)`;
        levSelect.appendChild(opt);
    }
    levSelect.value = curLev;
    
    document.getElementById('ac-sl').value = curSL;
    document.getElementById('ac-tp').value = curTP;
    
    const distSelect = document.getElementById('ac-entry-dist');
    if (![...distSelect.options].some(o => o.value == curEntryDist)) {
        const opt = document.createElement('option');
        opt.value = curEntryDist;
        opt.text = `${curEntryDist} points (Current)`;
        distSelect.appendChild(opt);
    }
    distSelect.value = curEntryDist;
    
    document.getElementById('admin-config-modal').style.display = 'flex';
}

function closeAdminConfigModal() {
    document.getElementById('admin-config-modal').style.display = 'none';
}

async function submitAdminConfig(e) {
    e.preventDefault();
    const userId = document.getElementById('ac-userid').value;
    
    try {
        const resp = await fetchAPI(`/admin/users/${userId}/trading-config`, {
            method: 'PUT',
            body: JSON.stringify({
                trading_timeframe: document.getElementById('ac-tf').value,
                max_leverage: parseInt(document.getElementById('ac-lev').value),
                position_size_pct: parseFloat(document.getElementById('ac-pct').value) / 100,
                stop_loss_points: parseFloat(document.getElementById('ac-sl').value),
                take_profit_points: parseFloat(document.getElementById('ac-tp').value),
                ema_distance_points: parseInt(document.getElementById('ac-entry-dist').value),
            })
        });
        showToast(`Config saved successfully! Delta Status: ${resp.delta_exchange_status}`);
        closeAdminConfigModal();
        loadAdminUsers();
    } catch(err) {
        // fetchAPI already handles showing error toasts
    }
}

