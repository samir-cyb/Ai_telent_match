/* The signed-in server session is authoritative for browser identity. */
(() => {
    const context = window.userContext || {};
    for (const role of ['student', 'company', 'admin']) {
        const key = role + 'Id';
        try {
            const stored = localStorage.getItem(role + '_id');
            if (role === 'company' && stored !== context[key]) localStorage.removeItem('last_viewed_job_id');
            for (const storageKey of [role + '_id', key]) {
                if (context[key]) localStorage.setItem(storageKey, context[key]);
                else localStorage.removeItem(storageKey);
            }
        } catch (_) { /* Browser storage can be disabled. */ }
    }
    try {
        const role = context.studentId ? 'student' : context.companyId ? 'company' : context.adminId ? 'admin' : '';
        if (role) localStorage.setItem('user_type', role);
        else localStorage.removeItem('user_type');
        if (!context.adminId) localStorage.removeItem('is_super_admin');
    } catch (_) { /* Server session checks still apply. */ }
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
        const url = new URL(input instanceof Request ? input.url : input, location.href);
        if (url.origin !== location.origin) return originalFetch(input, init);
        const method = (init.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
        const headers = new Headers(init.headers || (input instanceof Request ? input.headers : {}));
        if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
            const token = document.cookie.split('; ').find(item => item.startsWith('csrftoken='));
            if (token) headers.set('X-CSRFToken', decodeURIComponent(token.split('=').slice(1).join('=')));
        }
        const response = await originalFetch(input, {...init, headers, credentials: 'same-origin'});
        if (response.status === 401 && !location.pathname.includes('/login/')) {
            const role = context.studentId ? 'student' : context.companyId ? 'company' : context.adminId ? 'admin' : '';
            if (role) location.assign('/' + role + '/login/');
        }
        return response;
    };
})();

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
}

function safeHref(value) {
    try {
        if (!String(value || '').trim()) return '#';
        const url = new URL(String(value), location.href);
        return ['http:', 'https:'].includes(url.protocol) ? url.href : '#';
    } catch (_) { return '#'; }
}

function safeURL(value) { return escapeHtml(safeHref(value)); }
function jsAttr(value) { return escapeHtml(JSON.stringify(String(value ?? ''))); }

function mergeParsedItems(existing, incoming, key) {
    const result = [...(existing || [])];
    for (const item of incoming || []) {
        const identity = String(key(item)).trim().toLowerCase();
        if (identity && !result.some(old => String(key(old)).trim().toLowerCase() === identity)) result.push(item);
    }
    return result;
}
