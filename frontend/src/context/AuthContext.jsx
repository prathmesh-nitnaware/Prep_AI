import React, { createContext, useState, useContext, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  // authLoading: true only while restoring session from localStorage on first mount
  const [authLoading, setAuthLoading] = useState(true);
  // submitting: true only while a login/signup API call is in-flight
  const [submitting, setSubmitting] = useState(false);
  const navigate = useNavigate();

  const getApiUrl = () => {
    if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
    if (typeof window !== "undefined" && (window.location.port === "5173" || window.location.port === "5174")) {
      return "http://localhost:5000";
    }
    if (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")) {
      return "";
    }
    return "";
  };

  const API_URL = getApiUrl();

  // On mount: restore session from localStorage
  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    if (storedUser && storedUser !== 'undefined') {
      try {
        setUser(JSON.parse(storedUser));
      } catch (e) {
        localStorage.removeItem('user');
        localStorage.removeItem('token');
      }
    }
    setAuthLoading(false);
  }, []);

  /**
   * updateUserData
   * Allows components (like Profile/ResumeVault) to update the global user state
   * and local storage simultaneously without requiring a re-login.
   */
  const updateUserData = (updates) => {
    setUser(prevUser => {
      const updatedUser = { ...prevUser, ...updates };
      localStorage.setItem('user', JSON.stringify(updatedUser));
      return updatedUser;
    });
  };

  /**
   * login
   * Validates credentials against the backend database.
   * A user can ONLY log in if their account exists and is verified in MongoDB.
   */
  const login = async (email, password) => {
    setSubmitting(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();

      if (response.ok) {
        // Only set user if backend confirms credentials are valid in MongoDB
        setUser(data.user);
        localStorage.setItem('user', JSON.stringify(data.user));
        localStorage.setItem('token', data.token);
        setSubmitting(false);
        return { success: true, user: data.user };
      } else {
        setSubmitting(false);
        // Surface the exact backend error (wrong password, not found, not verified, etc.)
        return { success: false, message: data.error || "Login failed. Please check your credentials." };
      }
    } catch (error) {
      setSubmitting(false);
      return { success: false, message: "Connection error. Please check your internet and try again." };
    }
  };

  /**
   * signup
   * Creates account in the database. User must verify email before they can log in.
   */
  const signup = async (signupData) => {
    setSubmitting(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(signupData)
      });

      const data = await response.json();

      if (response.ok) {
        setSubmitting(false);
        return { success: true, message: data.message };
      } else {
        setSubmitting(false);
        return { success: false, message: data.error || "Signup failed. Please try again." };
      }
    } catch (error) {
      setSubmitting(false);
      return { success: false, message: "Connection error. Please check your internet and try again." };
    }
  };

  const loginWithGoogle = async (googlePayload) => {
    setSubmitting(true);
    try {
      const response = await fetch(`${API_URL}/api/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(googlePayload)
      });

      const data = await response.json();

      if (response.ok) {
        setUser(data.user);
        localStorage.setItem('user', JSON.stringify(data.user));
        localStorage.setItem('token', data.token);
        setSubmitting(false);
        return { success: true, user: data.user };
      } else {
        setSubmitting(false);
        return { success: false, message: data.error || "Google Sign-In failed." };
      }
    } catch (error) {
      setSubmitting(false);
      return { success: false, message: "Connection error. Please try again." };
    }
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('user');
    localStorage.removeItem('token');
    navigate('/');
  };

  const value = {
    user,
    isAuthenticated: !!user,
    // authLoading: used by ProtectedRoute to show skeleton while restoring session
    authLoading,
    // submitting: used by Login/Signup forms to show button loading state
    submitting,
    // Keep legacy 'loading' alias so nothing else breaks
    loading: authLoading,
    login,
    loginWithGoogle,
    signup,
    logout,
    updateUserData,
    API_URL
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
export default AuthContext;
