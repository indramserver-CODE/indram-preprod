import { Outlet } from 'react-router-dom';
import Topbar from './Topbar';
import useIdleLogout from '../../hooks/useIdleLogout';

export default function DashboardLayout() {
  useIdleLogout();
  return (
    <>
      <Topbar />
      <div className="layout">
        <div className="main">
          <Outlet />
        </div>
      </div>
    </>
  );
}