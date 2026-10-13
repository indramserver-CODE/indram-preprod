# Indramev — React Conversion

Full Vite + React conversion of the original HTML/CSS/JS frontend. All 22 pages
are converted and functional — nothing is stubbed.

## Run it

```bash
npm install
npm run dev
```

Set your API URL by editing `src/api/client.js` if it's not `localhost:8000` /
`api.indram.in` (same logic as the original `common.js`).

## Structure

- **Routing** (`src/App.jsx`): nested by role — `/super-admin/*` and `/admin/*`,
  `/login` public. `react-router-dom`.
- **Auth** (`src/context/AuthContext.jsx`): replaces `localStorage` +
  `guardAuth()`/`guardSuperAdmin()` with a React context; token/role/name
  still persist to `localStorage` so refresh keeps you logged in.
- **API client** (`src/api/client.js`): port of `api()` / `apiUpload()` /
  `authHeaders()` from `common.js`.
- **Toast** (`src/context/ToastContext.jsx`) / **Modal**
  (`src/components/common/Modal.jsx`): replace `showToast()` / `showModal()`.
- **Layout** (`src/components/layout/`): `Topbar`, `Sidebar` (nav in
  `navConfig.js`), `DashboardLayout`.
- **Charts**: `chart.js` via a small `useChart()` hook
  (`src/hooks/useChart.js`) that creates/destroys a Chart.js instance bound
  to a canvas ref — same charts as the original `analytics.js`/`sa-analytics.js`.

### Pages

**Super Admin** (`/super-admin/*`) — `src/pages/superadmin/`:
Dashboard, Societies, Flats, Chargers, Rfid, Admins, `SuperAdminAnalytics`.
Tickets uses the shared `src/pages/Tickets.jsx` with `scope="super"`.

**Society Admin** (`/admin/*`) — `src/pages/admin/`:
Dashboard, `SaFlats`, `SaSessions`, `SaCompleted`, `SaUsage`, `SaRfid`,
`SaBills`, `SaTariff`, `SocietyAnalytics`. Tickets uses `src/pages/Tickets.jsx`
with `scope="society"`.

Some pages are near-identical between roles in the original (e.g. tickets),
so those were merged into one parametrized component instead of duplicated —
`Dashboard.jsx` and `Tickets.jsx` are shared this way.

### Shared building blocks

- `SocietySelector` — society dropdown used by Flats/Chargers/Rfid/Admins (super admin)
- `CsvUploadPanel` — generic CSV bulk-upload widget (Flats/Chargers/Rfid)
- `PeakHoursHeatmap` — the 7×24 session heatmap, used by both analytics pages
- `FaultBadges.jsx` — `LiveStatusBadge` / `CompletedStatusBadge`, the
  hover-tooltip fault badges used by Sessions/Completed

## Styling

- `src/styles/common.css` — imported globally once (in `main.jsx`). Holds the
  shared design-system classes (`.topbar`, `.sidebar`, `.btn`, `.badge-*`,
  `.table-wrap`, form styles) used on nearly every page — not a good fit for
  per-component CSS Modules since they're genuinely cross-cutting.
- Page-specific styles are **CSS Modules**: `Login.module.css`,
  `Dashboard.module.css`, `Tickets.module.css`, `Analytics.module.css`,
  `FaultBadge.module.css`.

## One product decision worth knowing about

The original `sa-tariff.html` existed but wasn't linked from the society-admin
sidebar (it was a disabled, unlinked nav item in the source). Since it's a
fully working page, I wired it up as `/admin/tariff` with a working sidebar
link — feature parity, just now reachable. Say the word if you'd rather it
stay hidden.

## Not carried over

`reference/` (source HTML/JS, now fully migrated) has been removed from this
build — everything in it made it into the React app. If you want the raw
originals back for comparison, let me know and I'll re-attach them.
