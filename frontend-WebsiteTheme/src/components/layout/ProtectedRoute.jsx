import { Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

/**
 * Wrap a set of nested routes to require auth, and optionally a specific role.
 * requireRole: 'super_admin' | 'society_admin' | undefined (any authenticated role)
 */
export default function ProtectedRoute({ children, requireRole }) {
  const { isAuthenticated, role } = useAuth();

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (requireRole && role !== requireRole) return <Navigate to="/login" replace />;

  return children;
}
