// Web demo build: runs in any browser with no backend. Only features that compute in the page work.
export const WEB_DEMO = import.meta.env.VITE_FINHUB_WEB_DEMO === '1'

export const DEMO_COMMANDS = new Set(['learn', 'opt', 'sim', 'open', 'home', 'clear', 'error'])

export const DOWNLOAD_URL = 'https://github.com/adibmolla-rgb/FinHub#install'
