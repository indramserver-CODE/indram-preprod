import { NavLink, useNavigate } from 'react-router-dom';
import { useState, useRef, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { SUPER_ADMIN_NAV, SOCIETY_ADMIN_NAV } from './navConfig';

const TOPBAR_LOGO = { src: '/assets/brand-logo.svg', alt: 'Indram' };

export default function Topbar() {
  const { fullName, isSuperAdmin, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef(null);

  const allItems = isSuperAdmin ? SUPER_ADMIN_NAV : SOCIETY_ADMIN_NAV;
  const navItems = allItems.filter(item => item.key !== 'dashboard');
  const dashboardItem = allItems.find(item => item.key === 'dashboard');
  const dashboardPath = dashboardItem ? dashboardItem.to : '/dashboard';

  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="topbar">
      <div className="topbar-left">
        <img
          src={TOPBAR_LOGO.src}
          alt={TOPBAR_LOGO.alt}
          onClick={() => navigate(dashboardPath)}
          className="topbar-logo"
        />
        <div className="topbar-nav">
          {navItems.map(item => (
            <NavLink
              key={item.key}
              to={item.to}
              data-tooltip={item.desc}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
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