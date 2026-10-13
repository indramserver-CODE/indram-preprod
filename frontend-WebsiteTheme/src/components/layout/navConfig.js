// Nested-route sidebar config.
// super_admin pages live under /super-admin/*, society_admin pages under /admin/*

export const SUPER_ADMIN_NAV = [
  { key: 'dashboard',  label: 'Overview',   to: '/super-admin/dashboard',  desc: 'System overview' },
  { key: 'societies',  label: 'Societies',  to: '/super-admin/societies',  desc: 'Manage societies' },
  { key: 'flats',      label: 'Flats',      to: '/super-admin/flats',      desc: 'All flats' },
  { key: 'meters',     label: 'Meters',     to: '/super-admin/meters',     desc: 'MSEB meters' },
  { key: 'chargers',   label: 'Chargers',   to: '/super-admin/chargers',   desc: 'Charger management' },
  { key: 'rfid',       label: 'RFID',       to: '/super-admin/rfid',       desc: 'Card management' },
  { key: 'admins',       label: 'Admins',        to: '/super-admin/admins',        desc: 'Manage admins' },
  { key: 'indram-bills', label: 'Indram Bills',  to: '/super-admin/indram-bills',  desc: 'Platform invoice revenue' },
  { key: 'notifications', label: 'Notifications', to: '/super-admin/notifications', desc: 'Chargers to switch off / on' },
  { key: 'tickets',      label: 'Support',       to: '/super-admin/tickets',       desc: 'Support tickets' },
  { key: 'analytics',  label: 'Analytics',  to: '/super-admin/analytics',  desc: 'Reports & insights' },
];

export const SOCIETY_ADMIN_NAV = [
  { key: 'dashboard',  label: 'Dashboard',  to: '/admin/dashboard',   desc: 'Society overview' },
  { key: 'flats',      label: 'Chargers',   to: '/admin/flats',       desc: 'Manage chargers' },
  { key: 'meters',     label: 'Meters',     to: '/admin/meters',      desc: 'Your MSEB meters' },
  { key: 'sessions',   label: 'Live',       to: '/admin/sessions',    desc: 'Live sessions' },
  { key: 'completed',  label: 'History',    to: '/admin/completed',   desc: 'Session history' },
  { key: 'usage',      label: 'Usage',      to: '/admin/usage',       desc: 'Consumption data' },
  { key: 'rfid',       label: 'RFID',       to: '/admin/rfid',        desc: 'Card management' },
  { key: 'bills',        label: 'Bills',        to: '/admin/bills',          desc: 'Billing history' },
  { key: 'indram-bills', label: 'Indram Bill',  to: '/admin/indram-bills',   desc: 'Platform invoice' },
  { key: 'billing-settings', label: 'Billing Settings', to: '/admin/billing-settings', desc: 'Letterhead & payment details' },
  { key: 'tariff',       label: 'Tariff',       to: '/admin/tariff',         desc: 'Rate history' },
  { key: 'tickets',    label: 'Support',    to: '/admin/tickets',     desc: 'Support tickets' },
  { key: 'analytics',  label: 'Analytics',  to: '/admin/analytics',   desc: 'Reports & insights' },
];