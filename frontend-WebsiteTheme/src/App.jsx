import { Routes, Route, Navigate } from 'react-router-dom';
import DashboardLayout from './components/layout/DashboardLayout';
import ProtectedRoute from './components/layout/ProtectedRoute';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Dashboard from './pages/superadmin/Dashboard';
import Tickets from './pages/Tickets';

import Societies from './pages/superadmin/Societies';
import Flats from './pages/superadmin/Flats';
import Meters from './pages/superadmin/Meters';
import Chargers from './pages/superadmin/Chargers';
import Rfid from './pages/superadmin/Rfid';
import Admins from './pages/superadmin/Admins';
import SuperAdminAnalytics from './pages/superadmin/SuperAdminAnalytics';

import SaFlats from './pages/admin/SaFlats';
import SaDashboard from './pages/admin/SaDashboard';
import SaSessions from './pages/admin/SaSessions';
import SaCompleted from './pages/admin/SaCompleted';
import SaUsage from './pages/admin/SaUsage';
import SaRfid from './pages/admin/SaRfid';
import SaBills from './pages/admin/SaBills';
import SaTariff from './pages/admin/SaTariff';
import SaMeters from './pages/admin/SaMeters';
import SaIndramBills from './pages/admin/SaIndramBills';
import SocietyAnalytics from './pages/admin/SocietyAnalytics';
import IndramBills from './pages/superadmin/IndramBills';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      {/* Super Admin section */}
      <Route
        path="/super-admin"
        element={
          <ProtectedRoute requireRole="super_admin">
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route path="dashboard"  element={<Dashboard />} />
        <Route path="societies"  element={<Societies />} />
        <Route path="flats"      element={<Flats />} />
        <Route path="meters"     element={<Meters />} />
        <Route path="chargers"   element={<Chargers />} />
        <Route path="rfid"       element={<Rfid />} />
        <Route path="admins"       element={<Admins />} />
        <Route path="indram-bills" element={<IndramBills />} />
        <Route path="tickets"      element={<Tickets scope="super" />} />
        <Route path="analytics"  element={<SuperAdminAnalytics />} />
      </Route>

      {/* Society Admin section */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute requireRole="society_admin">
            <DashboardLayout />
          </ProtectedRoute>
        }
      >
        <Route path="dashboard"  element={<SaDashboard />} />
        <Route path="flats"      element={<SaFlats />} />
        <Route path="meters"     element={<SaMeters />} />
        <Route path="sessions"   element={<SaSessions />} />
        <Route path="completed"  element={<SaCompleted />} />
        <Route path="usage"      element={<SaUsage />} />
        <Route path="rfid"       element={<SaRfid />} />
        <Route path="bills"        element={<SaBills />} />
        <Route path="indram-bills" element={<SaIndramBills />} />
        <Route path="tariff"       element={<SaTariff />} />
        <Route path="tickets"    element={<Tickets scope="society" />} />
        <Route path="analytics"  element={<SocietyAnalytics />} />
      </Route>

      <Route path="/"  element={<Navigate to="/login" replace />} />
      <Route path="*"  element={<Navigate to="/login" replace />} />
    </Routes>
  );
}