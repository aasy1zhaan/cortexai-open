// Client configuration for static hosting. The FastAPI server replaces this file at
// /assets/js/config.js with {demo: false}, so the deployed site always uses the real API.
// A static preview can add {demo_login, demo_pw: {salt, iter, hash}} (PBKDF2-SHA256) to allow
// one preview sign-in on the bundled synthetic data; without it, demo sign-in is disabled.
window.CORTEX_CONFIG = { demo: true, single_account: true };
