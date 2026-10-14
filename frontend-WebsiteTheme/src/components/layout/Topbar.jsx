import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import { SUPER_ADMIN_NAV, SOCIETY_ADMIN_NAV } from './navConfig';

const TOPBAR_LOGO = { src: '/assets/brand-logo.svg', alt: 'Indram' };
const NAV_GAP = 10;       // matches .topbar-nav gap
const MORE_WIDTH = 96;    // room kept for the "More ▾" button

export default function Topbar() {
  const { fullName, isSuperAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const menuRef = useRef(null);
  const moreRef = useRef(null);
  const navRef = useRef(null);
  const measureRef = useRef(null);

  const allItems = isSuperAdmin ? SUPER_ADMIN_NAV : SOCIETY_ADMIN_NAV;
  const navItems = allItems.filter(item => item.key !== 'dashboard');
  const dashboardItem = allItems.find(item => item.key === 'dashboard');
  const dashboardPath = dashboardItem ? dashboardItem.to : '/dashboard';

  // Show as many links as fit; the rest go under "More" so the bar never widens the page
  const [visibleCount, setVisibleCount] = useState(navItems.length);

  const fit = useCallback(() => {
    const nav = navRef.current, measure = measureRef.current;
    if (!nav || !measure) return;
    const widths = [...measure.children].map(el => el.getBoundingClientRect().width);
    const available = nav.clientWidth;
    const total = widths.reduce((sum, w) => sum + w, 0) + NAV_GAP * Math.max(widths.length - 1, 0);
    if (total <= available) { setVisibleCount(widths.length); return; }
    let used = MORE_WIDTH, count = 0;
    for (const w of widths) {
      if (used + w + NAV_GAP > available) break;
      used += w + NAV_GAP;
      count += 1;
    }
    setVisibleCount(count);
  }, []);

  useLayoutEffect(() => {
    fit();
    const observer = new ResizeObserver(fit);
    if (navRef.current) observer.observe(navRef.current);
    return () => observer.disconnect();
  }, [fit, navItems.length]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
      if (moreRef.current && !moreRef.current.contains(e.target)) setMoreOpen(false);
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => { setMoreOpen(false); }, [location.pathname]);

  const shown = navItems.slice(0, visibleCount);
  const hidden = navItems.slice(visibleCount);
  const hiddenActive = hidden.some(item => location.pathname.startsWith(item.to));

  return (
    <div className="topbar">
      <div className="topbar-left">
        <img
          src={TOPBAR_LOGO.src}
          alt={TOPBAR_LOGO.alt}
          onClick={() => navigate(dashboardPath)}
          className="topbar-logo"
        />
        <div className="topbar-nav" ref={navRef}>
          {shown.map(item => (
            <NavLink
              key={item.key}
              to={item.to}
              data-tooltip={item.desc}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}

          {hidden.length > 0 && (
            <div className="nav-more" ref={moreRef}>
              <button
                className={`nav-item nav-more-trigger ${hiddenActive ? 'active' : ''}`}
                onClick={() => setMoreOpen(o => !o)}
                aria-expanded={moreOpen}
              >
                More <span className={`chevron ${moreOpen ? 'open' : ''}`}>▾</span>
              </button>
              {moreOpen && (
                <div className="user-dropdown nav-more-menu">
                  {hidden.map(item => (
                    <NavLink
                      key={item.key}
                      to={item.to}
                      className={({ isActive }) => `dropdown-item nav-more-item ${isActive ? 'active' : ''}`}
                    >
                      {item.label}
                      <span className="nav-more-desc">{item.desc}</span>
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Off-screen copy of every link, used only to measure their widths */}
          <div className="nav-measure" ref={measureRef} aria-hidden="true">
            {navItems.map(item => (
              <span key={item.key} className="nav-item">{item.label}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="topbar-right" ref={menuRef}>
        <button
          className="user-menu-trigger"
          onClick={() => setMenuOpen(o => !o)}
        >
          {fullName}
          <span className={`chevron ${menuOpen ? 'open' : ''}`}>▾</span>
        </button>

        {menuOpen && (
          <div className="user-dropdown">
            <button className="dropdown-item" onClick={() => {}}>
              Settings
            </button>
            <button className="dropdown-item dropdown-item-danger" onClick={logout}>
              Logout
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
