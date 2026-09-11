import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useGoogleLogin } from '@react-oauth/google';
import { Mail, Lock, AlertCircle, Sparkles, Layers, Target, ShieldCheck } from 'lucide-react';
import './Login.css';

const Login = () => {
  const [formData, setFormData] = useState({ email: '', password: '' });
  const [error, setError] = useState(null);
  const { login, loginWithGoogle, user, submitting } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/dashboard';

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    if (error) setError(null);
  };

  const handleGoogleSuccess = (userData) => {
    const currentUser = userData || JSON.parse(localStorage.getItem('user') || '{}');
    if (currentUser?.role === 'admin') {
      navigate('/admin', { replace: true });
    } else if (currentUser?.onboarding_completed === false) {
      navigate('/onboarding', { replace: true });
    } else {
      navigate(from, { replace: true });
    }
  };

  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      try {
        const userInfoRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: { Authorization: `Bearer ${tokenResponse.access_token}` },
        });
        const profile = await userInfoRes.json();

        if (profile?.email) {
          const result = await loginWithGoogle({
            email: profile.email,
            name: profile.name || profile.given_name || profile.email.split('@')[0],
            google_id: profile.sub || `google_${Date.now()}`,
            picture: profile.picture
          });

          if (result.success) {
            handleGoogleSuccess(result.user);
          } else {
            setError(result.message || 'Google authentication failed.');
          }
        } else {
          setError('Failed to retrieve user profile from Google.');
        }
      } catch (err) {
        setError('Connection error during Google Sign-In.');
      }
    },
    onError: (errorResponse) => {
      console.error('Google Sign-In Error:', errorResponse);
      setError('Google Sign-In was cancelled or failed.');
    }
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.email || !formData.password) {
      setError('Please enter both your email and password.');
      return;
    }

    const result = await login(formData.email, formData.password);

    if (result.success) {
      if (result.user && result.user.role === 'admin') {
        navigate('/admin', { replace: true });
      } else if (result.user && result.user.onboarding_completed === false) {
        navigate('/onboarding', { replace: true });
      } else {
        navigate(from, { replace: true });
      }
    } else {
      setError(result.message || 'Invalid email or password. Please try again.');
    }
  };

  return (
    <div className="auth-page-root">
      <div className="auth-workspace-container">
        {/* Left Column: Product Value Pillars */}
        <div className="auth-brand-column">
          <Link to="/" className="auth-brand-logo">
            <div className="auth-logo-icon">
              <Sparkles size={18} />
            </div>
            <span className="auth-logo-text">PREP AI</span>
          </Link>

          <div>
            <h1 className="auth-hero-title">
              Practice the interview before the interview.
            </h1>
            <p className="auth-hero-subtitle" style={{ marginTop: '0.6rem' }}>
              Adaptive technical, system design, and behavioral mock interviews calibrated for engineering campus placements.
            </p>
          </div>

          <div className="auth-feature-list">
            <div className="auth-feature-item">
              <div className="auth-feature-icon-box">
                <Layers size={15} />
              </div>
              <div className="auth-feature-content">
                <span className="auth-feature-heading">5-Stage Adaptive Progression</span>
                <p className="auth-feature-desc">
                  Fundamentals, applied problem solving, deep technical depth, system architecture, and behavioral STAR questions.
                </p>
              </div>
            </div>

            <div className="auth-feature-item">
              <div className="auth-feature-icon-box">
                <Target size={15} />
              </div>
              <div className="auth-feature-content">
                <span className="auth-feature-heading">Explainable Performance Audits</span>
                <p className="auth-feature-desc">
                  Objective evidence breakdowns, trade-off analysis, technical gap probing, and vocal delivery coaching.
                </p>
              </div>
            </div>

            <div className="auth-feature-item">
              <div className="auth-feature-icon-box">
                <ShieldCheck size={15} />
              </div>
              <div className="auth-feature-content">
                <span className="auth-feature-heading">Role-Specific Placement Tracks</span>
                <p className="auth-feature-desc">
                  Tailored questioning for Backend, Frontend, Full Stack, SRE, and ML/AI engineering roles.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Clean Login Card */}
        <div className="auth-form-card">
          <div className="auth-card-header">
            <h2 className="auth-card-title">Sign in to your account</h2>
            <p className="auth-card-subtitle">
              Enter your placement preparation credentials.
            </p>
          </div>

          {error && (
            <div className="auth-alert-banner">
              <AlertCircle size={16} style={{ flexShrink: 0 }} />
              <span>{error}</span>
            </div>
          )}

          <button
            type="button"
            className="btn-google-auth"
            onClick={() => googleLogin()}
            disabled={submitting}
          >
            <svg className="google-icon-svg" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
            </svg>
            <span>Continue with Google</span>
          </button>

          <div className="auth-divider">
            <div className="auth-divider-line"></div>
            <span className="auth-divider-text">Or email</span>
            <div className="auth-divider-line"></div>
          </div>

          <form onSubmit={handleSubmit} className="auth-form">
            <div className="form-group">
              <label className="form-label" htmlFor="email">Email Address</label>
              <div className="input-with-icon">
                <div className="input-icon-slot">
                  <Mail size={15} />
                </div>
                <input
                  id="email"
                  type="email"
                  name="email"
                  className="auth-input-field"
                  placeholder="student@example.com"
                  value={formData.email}
                  onChange={handleChange}
                  autoComplete="email"
                  required
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="password">Password</label>
              <div className="input-with-icon">
                <div className="input-icon-slot">
                  <Lock size={15} />
                </div>
                <input
                  id="password"
                  type="password"
                  name="password"
                  className="auth-input-field"
                  placeholder="••••••••"
                  value={formData.password}
                  onChange={handleChange}
                  autoComplete="current-password"
                  required
                />
              </div>
            </div>

            <div className="auth-options-row">
              <label className="auth-remember-label">
                <input type="checkbox" />
                <span>Remember me</span>
              </label>
              <Link to="/forgot-password" className="auth-forgot-link">
                Forgot password?
              </Link>
            </div>

            <button
              type="submit"
              className="btn-auth-submit"
              disabled={submitting}
            >
              {submitting ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>

          <div className="auth-card-footer">
            <span>Don't have an account? </span>
            <Link to="/signup" className="auth-switch-link">
              Create account
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;