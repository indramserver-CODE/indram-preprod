import { createContext, useContext, useState, useCallback } from 'react';
import { api, apiPublic, getToken, getRole, getFullName } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(getToken());
  const [role, setRole] = useState(getRole());
  const [fullName, setFullName] = useState(getFullName());

  const login = useCallback(async (email, password) => {
    const data = await apiPublic('POST', '/api/auth/login', { email, password });
    localStorage.setItem('token', data.access_token);
    localStorage.setItem('role', data.role);
    localStorage.setItem('full_name', data.full_name || '');
    setToken(data.access_token);
    setRole(data.role);
    setFullName(data.full_name || '');
    return data;
  }, []);

  const logout = useCallback(() => {
    api('POST', '/api/auth/logout').catch(() => {}).finally(() => {
      localStorage.clear();
      setToken(null);
      setRole(null);
      setFullName('Admin');
    });
  }, []);

  const value = {
    token,
    role,
    fullName,
    isAuthenticated: !!token,
    isSuperAdmin: role === 'super_admin',
    isSocietyAdmin: role === 'society_admin',
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
