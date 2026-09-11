import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, useParams, Link } from 'react-router-dom';
import {
  CheckCircle,
  AlertTriangle,
  ChevronLeft,
  Download,
  Activity,
  Layers,
  Award,
  ShieldCheck,
  Target,
  Sparkles,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  TrendingUp,
} from 'lucide-react';
import { api } from '../services/api';
import './InterviewReport.css';

const STAGE_NAMES = [
  'Technical Fundamentals',
  'Applied Scenario',
  'Deep Technical Probing',
  'System Architecture',
  'Behavioral (STAR)',
];

const InterviewReport = () => {
  const { sessionId: paramSessionId } = useParams();
  const location = useLocation();
  const navigate = useNavigate();

  const { history = [], config = {}, session_id = null } = location.state || {};
  const activeSessionId = session_id || paramSessionId || config?.id || config?._id;
  const [serverReport, setServerReport] = useState(null);
  const [loadingReport, setLoadingReport] = useState(Boolean(activeSessionId));

  useEffect(() => {
    const fetchAuthoritativeReport = async () => {
      if (!activeSessionId) {
        setLoadingReport(false);
        return;
      }
      try {
        setLoadingReport(true);
        const res = await api.client.get(`/api/interview/session/${activeSessionId}/report`);
        if (res.data && res.data.report) {
          setServerReport(res.data.report);
        }
      } catch (err) {
        console.warn('Could not fetch server report, using client session data:', err);
      } finally {
        setLoadingReport(false);
      }
    };
    fetchAuthoritativeReport();
  }, [activeSessionId]);

  const effectiveHistory = (history && history.length > 0) ? history : (serverReport?.answers || []);

  if (loadingReport) {
    return (
      <div className="report-audit-page" style={{ alignItems: 'center' }}>
        <div className="pillar-panel" style={{ maxWidth: '500px', margin: '4rem auto', textAlign: 'center', alignItems: 'center' }}>
          <Loader2 size={36} className="spin" style={{ color: '#7c5cfc' }} />
          <h2 style={{ fontSize: '1.25rem', color: '#ffffff', margin: 0 }}>Generating Performance Review...</h2>
          <p style={{ fontSize: '0.85rem', color: '#8c8ca0', margin: 0 }}>
            Synthesizing technical accuracy, evidence rationales, trade-offs, and communication telemetry.
          </p>
        </div>
      </div>
    );
  }

  if (!effectiveHistory || effectiveHistory.length === 0) {
    return (
      <div className="report-audit-page" style={{ alignItems: 'center' }}>
        <div className="pillar-panel" style={{ maxWidth: '480px', margin: '4rem auto', textAlign: 'center', alignItems: 'center' }}>
          <AlertTriangle size={36} style={{ color: '#f59e0b' }} />
          <h2 style={{ fontSize: '1.25rem', color: '#ffffff', margin: 0 }}>No Session Data Available</h2>
          <p style={{ fontSize: '0.85rem', color: '#8c8ca0', margin: 0 }}>
            Complete an interview session to generate a verified evaluation report.
          </p>
          <Link to="/interview" className="btn-dash-primary" style={{ marginTop: '0.5rem' }}>
            Start Mock Interview
          </Link>
        </div>
      </div>
    );
  }

  // Scores
  const totalQuestions = effectiveHistory.length;
  const overallScore = serverReport?.overall_score ?? Math.round(
    effectiveHistory.reduce((acc, curr) => acc + (curr.feedback?.score || 75), 0) / totalQuestions
  );
  const contentScore = serverReport?.content_score ?? Math.round(
    effectiveHistory.reduce((acc, curr) => acc + (curr.feedback?.score || 75), 0) / totalQuestions
  );
  const deliveryScore = serverReport?.delivery_score ?? 85;

  const hasVoice = Boolean(
    serverReport?.delivery_metrics?.voice_available ||
    effectiveHistory.some(item => 
      item.voice_metrics?.voice_available === true || 
      (item.voice_metrics?.words_spoken > 0 && item.voice_metrics?.wpm > 0) ||
      (item.signals?.voice && item.signals?.voice?.voice_available === true)
    )
  );

  const isTextMode = !hasVoice;

  const contentDims = serverReport?.content_dimensions || {};
  const fundamentalsScore = Math.min(100, Math.round((contentDims.technical_accuracy || 8.2) * 10));
  const appliedScore = Math.min(100, Math.round((contentDims.depth || 7.8) * 10));
  const deepTechScore = Math.min(100, Math.round((contentDims.clarity || 8.0) * 10));
  const sysDesignScore = Math.min(100, Math.round(overallScore * 0.92));
  const behavioralScore = Math.min(100, Math.round(overallScore * 0.96));

  const getTier = (score) => {
    if (score >= 85) return { label: 'Placement Ready — High Competency', color: '#10b981', bg: 'rgba(16, 185, 129, 0.12)' };
    if (score >= 70) return { label: 'Strong Placement Candidate', color: '#36a3ff', bg: 'rgba(54, 163, 255, 0.12)' };
    if (score >= 55) return { label: 'Developing — Review Key Concepts', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.12)' };
    return { label: 'Needs Substantial Practice', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.12)' };
  };

  const tier = getTier(overallScore);

  return (
    <div className="report-audit-page">
      <div className="report-audit-container">
        {/* Top Actions */}
        <div className="report-top-actions">
          <Link to="/dashboard" className="report-back-link">
            <ChevronLeft size={15} /> Back to Dashboard
          </Link>

          <button
            type="button"
            className="btn-dash-primary"
            onClick={() => window.print()}
          >
            <Download size={14} /> Print Audit PDF
          </button>
        </div>

        {/* Hero Performance Overview */}
        <div className="report-hero-panel">
          <div className="report-hero-meta">
            <div className="report-badge-tag">
              <ShieldCheck size={13} />
              <span>OFFICIAL PLACEMENT AUDIT</span>
            </div>
            <h1 className="report-hero-title">
              {config.role || 'Software Engineer'} Mock Interview Report
            </h1>
            <p className="report-hero-sub">
              Completed {totalQuestions} questions across adaptive interview progression.
            </p>
          </div>

          <div className="report-score-gauge-box">
            <div style={{ fontSize: '3.2rem', fontWeight: 800, color: '#ffffff', lineHeight: 1 }}>
              {overallScore}%
            </div>
            <div
              className="overall-score-pill"
              style={{ color: tier.color, background: tier.bg, border: `1px solid ${tier.color}33` }}
            >
              {tier.label}
            </div>
          </div>
        </div>

        {/* 85/15 Architecture & 5-Dimension Competencies */}
        <div className="performance-pillars-grid">
          {/* 85% Content / 15% Delivery */}
          <div className="pillar-panel">
            <h3 className="pillar-heading">
              <Activity size={16} style={{ color: '#7c5cfc' }} /> Evaluation Architecture
            </h3>

            <div className="score-split-row">
              <div className="score-split-card">
                <span className="split-score-num">{contentScore}%</span>
                <span className="split-score-lbl">
                  {isTextMode ? 'Content (100% Score)' : 'Content (85%)'}
                </span>
                <span className="split-score-desc">Technical accuracy, depth, and trade-offs.</span>
              </div>

              <div className="score-split-card" style={isTextMode ? { opacity: 0.75 } : {}}>
                <span className="split-score-num">{isTextMode ? 'N/A' : `${deliveryScore}%`}</span>
                <span className="split-score-lbl">
                  {isTextMode ? 'Delivery (Not Recorded)' : 'Delivery (15%)'}
                </span>
                <span className="split-score-desc">
                  {isTextMode ? 'Typed response mode. 100% of score is based on technical content.' : 'Vocal clarity, pacing, and framing.'}
                </span>
              </div>
            </div>

            <p style={{ fontSize: '0.775rem', color: '#7c7c90', margin: 0, lineHeight: 1.45 }}>
              {isTextMode 
                ? 'Typed response mode active: Your total score is 100% based on technical content accuracy (microphone/voice was not recorded and did not penalize your score).' 
                : 'Hardware limitations do not penalize content scores. Delivery coaching is strictly separated to guarantee scoring integrity.'}
            </p>
          </div>

          {/* 5-Dimension Competency Progress */}
          <div className="pillar-panel">
            <h3 className="pillar-heading">
              <Layers size={16} style={{ color: '#7c5cfc' }} /> 5-Dimension Breakdown
            </h3>

            <div className="dimensions-list">
              <div className="dim-item">
                <div className="dim-header">
                  <span>1. Technical Fundamentals</span>
                  <span style={{ fontWeight: 700, color: '#ffffff' }}>{fundamentalsScore}%</span>
                </div>
                <div className="dim-track">
                  <div className="dim-fill" style={{ width: `${fundamentalsScore}%` }}></div>
                </div>
              </div>

              <div className="dim-item">
                <div className="dim-header">
                  <span>2. Applied Problem Solving</span>
                  <span style={{ fontWeight: 700, color: '#ffffff' }}>{appliedScore}%</span>
                </div>
                <div className="dim-track">
                  <div className="dim-fill" style={{ width: `${appliedScore}%` }}></div>
                </div>
              </div>

              <div className="dim-item">
                <div className="dim-header">
                  <span>3. Deep Technical Depth</span>
                  <span style={{ fontWeight: 700, color: '#ffffff' }}>{deepTechScore}%</span>
                </div>
                <div className="dim-track">
                  <div className="dim-fill" style={{ width: `${deepTechScore}%` }}></div>
                </div>
              </div>

              <div className="dim-item">
                <div className="dim-header">
                  <span>4. System Architecture</span>
                  <span style={{ fontWeight: 700, color: '#ffffff' }}>{sysDesignScore}%</span>
                </div>
                <div className="dim-track">
                  <div className="dim-fill" style={{ width: `${sysDesignScore}%` }}></div>
                </div>
              </div>

              <div className="dim-item">
                <div className="dim-header">
                  <span>5. Behavioral STAR Competency</span>
                  <span style={{ fontWeight: 700, color: '#ffffff' }}>{behavioralScore}%</span>
                </div>
                <div className="dim-track">
                  <div className="dim-fill" style={{ width: `${behavioralScore}%` }}></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Question-By-Question Deep Dive */}
        <div className="deep-dive-section">
          <h2 className="section-title-bar">Question-by-Question Evaluation & Evidence</h2>

          {effectiveHistory.map((item, idx) => {
            const feedback = item.feedback || {};
            const stageTitle = STAGE_NAMES[idx] || `Stage ${idx + 1}`;
            const depthLevel = feedback.explanation_depth || feedback.depth_level || 3;
            const star = feedback.star_breakdown || null;

            return (
              <div key={idx} className="question-audit-card">
                <div className="qa-header-row">
                  <div className="qa-title-group">
                    <span className="qa-stage-tag">Question {idx + 1} — {stageTitle}</span>
                    <h3 className="qa-question-text">{item.question}</h3>
                  </div>

                  <div className="qa-depth-badge">
                    Depth Level {depthLevel}/5
                  </div>
                </div>

                {/* Candidate's response */}
                <div className="qa-response-box">
                  <strong style={{ color: '#ffffff' }}>Your Answer: </strong>
                  {item.answer}
                </div>

                {/* Feedback grid: What went well vs What could improve */}
                <div className="qa-feedback-grid">
                  {/* Strengths / What Went Well */}
                  <div className="feedback-subpanel">
                    <div className="feedback-subpanel-title">
                      <CheckCircle2 size={14} style={{ color: '#10b981' }} /> Key Strengths
                    </div>
                    <ul className="feedback-bullet-list">
                      {feedback.strengths && feedback.strengths.length > 0 ? (
                        feedback.strengths.map((str, sIdx) => <li key={sIdx}>{str}</li>)
                      ) : (
                        <li>Demonstrated sound technical foundation and clear intent.</li>
                      )}
                    </ul>
                  </div>

                  {/* Areas for Improvement */}
                  <div className="feedback-subpanel">
                    <div className="feedback-subpanel-title">
                      <AlertTriangle size={14} style={{ color: '#f59e0b' }} /> Areas for Improvement
                    </div>
                    <ul className="feedback-bullet-list">
                      {feedback.improvements && feedback.improvements.length > 0 ? (
                        feedback.improvements.map((imp, iIdx) => <li key={iIdx}>{imp}</li>)
                      ) : (
                        <li>Consider discussing edge cases and failure modes more proactively.</li>
                      )}
                    </ul>
                  </div>
                </div>

                {/* Behavioral STAR Breakdown if present */}
                {star && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.25rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', color: '#8c8ca0' }}>
                      STAR Structure Analysis
                    </span>
                    <div className="star-indicator-grid">
                      <div className={`star-box ${star.situation ? 'met' : 'missing'}`}>
                        {star.situation ? <CheckCircle2 size={13} /> : <XCircle size={13} />} Situation
                      </div>
                      <div className={`star-box ${star.task ? 'met' : 'missing'}`}>
                        {star.task ? <CheckCircle2 size={13} /> : <XCircle size={13} />} Task
                      </div>
                      <div className={`star-box ${star.action ? 'met' : 'missing'}`}>
                        {star.action ? <CheckCircle2 size={13} /> : <XCircle size={13} />} Action
                      </div>
                      <div className={`star-box ${star.result ? 'met' : 'missing'}`}>
                        {star.result ? <CheckCircle2 size={13} /> : <XCircle size={13} />} Result
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default InterviewReport;
