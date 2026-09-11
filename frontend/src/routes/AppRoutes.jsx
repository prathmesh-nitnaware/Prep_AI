import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from '../components/layout/Layout';
import ProtectedRoute from '../components/ProtectedRoute';

// Public Pages
import Landing from '../pages/Landing';
import Login from '../pages/Login';
import Signup from '../pages/Signup';
import ForgotPassword from '../pages/ForgotPassword';
import ResetPassword from '../pages/ResetPassword';
import VerifyEmail from '../pages/VerifyEmail';

// Protected Pages
import Dashboard from '../pages/Dashboard';
import Profile from '../pages/Profile';
import ResumeUpload from '../pages/ResumeUpload';
import ResumeResult from '../pages/ResumeResult'; 
import Onboarding from '../pages/Onboarding'; 
import AdminDashboard from '../pages/AdminDashboard'; 
import AdminUsersList from '../pages/AdminUsersList';

// Interview Flow
import Interview from '../pages/Interview'; 
import InterviewSession from '../pages/InterviewSession'; 
import InterviewLive from '../pages/InterviewLive';       
import InterviewReport from '../pages/InterviewReport';   

// Coding Dojo Flow (The Unified "HackerRank" Module)
import CodingDojo from '../pages/CodingDojo';

const AppRoutes = () => {
  return (
    <Routes>
      
      {/* --- PUBLIC ROUTES --- */}
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/verify-email" element={<VerifyEmail />} />

      {/* --- PROTECTED ROUTES --- */}
      <Route element={<ProtectedRoute />}>
        
        {/* Immersive/Fullscreen Routes */}
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/interview/session" element={<InterviewSession />} />
        <Route path="/interview/live" element={<InterviewLive />} />
        
        {/* Standard App Routes (Wrapped in Global Layout & Navbar) */}
        <Route element={<Layout />}>
          
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/profile" element={<Profile />} />
          
          {/* Resume Flow */}
          <Route path="/resume/upload" element={<ResumeUpload />} />
          <Route path="/resume/result" element={<ResumeResult />} />

          {/* Voice Interview Config & Report */}
          <Route path="/interview/setup" element={<Interview />} /> 
          <Route path="/interview/report" element={<InterviewReport />} />
          <Route path="/interview/report/:sessionId" element={<InterviewReport />} />
          
          {/* Coding Dojo - HackerRank Style Implementation */}
          <Route path="/coding/dojo" element={<CodingDojo />} />
          
          {/* Admin Panel */}
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/users" element={<AdminUsersList />} />
          
        </Route>
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

export default AppRoutes;
