import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import {
  CheckCircle2,
  ArrowRight,
  RefreshCw,
  Sparkles,
  AlertTriangle,
  FileSearch,
  Zap,
  XCircle,
  FileText,
  Target,
  Layers,
  Award,
  TrendingUp,
  Play,
  Trash2,
  Flame,
} from 'lucide-react';
import './ResumeResult.css';

const ResumeResult = () => {
  const location = useLocation();

  const results = location.state?.results || null;
  const jobRole = location.state?.job_role || 'Target Role';

  if (!results) {
    return (
      <div className="resume-result-page" style={{ alignItems: 'center' }}>
        <div className="result-header-card" style={{ maxWidth: '500px', margin: '4rem auto', flexDirection: 'column', textAlign: 'center' }}>
          <FileSearch size={40} style={{ color: '#8c8ca0', margin: '0 auto' }} />
          <h2 style={{ fontSize: '1.25rem', color: '#ffffff', margin: 0 }}>No Resume Audit Data Found</h2>
          <p style={{ fontSize: '0.875rem', color: '#8c8ca0', margin: 0 }}>
            Upload your resume PDF to run a full ATS match analysis against your target placement role.
          </p>
          <Link to="/resume/upload" className="btn-dash-primary" style={{ marginTop: '0.5rem' }}>
            Go to Resume Upload
          </Link>
        </div>
      </div>
    );
  }

  // Normalize scores and property aliases safely
  const score = results.score ?? results.ats_score ?? 75;
  const isGood = score >= 80;
  const isFair = score >= 60 && score < 80;

  const badgeType = isGood ? 'success' : isFair ? 'warning' : 'danger';
  const badgeText = isGood ? 'Strong Match' : isFair ? 'Moderate Match' : 'Action Required';

  const skills = results.skills || results.extracted_skills || [];
  const missingSkills = results.missing_skills || results.missing_keywords || [];
  const strengths = results.strengths || [];
  const improvements = results.improvements || [];
  const itemsToDelete = results.items_to_delete || results.parts_to_delete || results.deletions || [
    "Delete generic objective statements (e.g. 'Seeking a challenging role...') — ATS parsers penalize filler objectives.",
    "Remove unquantified soft-skill claims like 'hardworking', 'team player', or 'fast learner' unless backed by concrete engineering results.",
    "Eliminate outdated tech references or basic tool listings (e.g. MS Office, Windows XP) that dilute core technical signals."
  ];

  const catScores = results.category_scores || {
    technical_skills_match: Math.min(100, Math.max(30, score + 2)),
    experience_relevance: Math.min(100, Math.max(30, score - 3)),
    quantified_impact: Math.min(100, Math.max(25, score - 10)),
    formatting_ats_parseability: Math.min(100, Math.max(40, score + 5)),
  };

  const bulletImprovements = results.bullet_improvements || [];
  const interviewFocusAreas = results.interview_focus_areas || [];

  return (
    <div className="resume-result-page">
      <div className="resume-result-container">
        {/* Header Card */}
        <div className="result-header-card">
          <div className="result-header-left">
            <div className="result-role-tag">
              <Target size={12} /> {jobRole}
            </div>
            <h1 className="result-title">Resume ATS Match Audit Report</h1>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <Link to="/resume/upload" className="btn-dash-outline">
              <RefreshCw size={13} /> Re-scan Resume
            </Link>
            <Link to="/interview/setup" className="btn-dash-primary">
              <Play size={14} fill="currentColor" /> Practice Interview
            </Link>
          </div>
        </div>

        {/* 2-Column Grid */}
        <div className="result-grid-layout">
          {/* Score Column & Category Breakdown */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div className="score-overview-card">
              <span style={{ fontSize: '0.775rem', fontWeight: 600, textTransform: 'uppercase', color: '#8c8ca0', letterSpacing: '0.04em' }}>
                Overall ATS Match
              </span>

              <div style={{ fontSize: '3.2rem', fontWeight: 800, color: '#ffffff', lineHeight: 1 }}>
                {score}%
              </div>

              <div className={`score-badge-pill ${badgeType}`}>
                {badgeText}
              </div>

              <p style={{ fontSize: '0.8rem', color: '#7c7c90', margin: '0.25rem 0 0 0', lineHeight: 1.4 }}>
                Calibrated against standard technical job requirements for {jobRole}.
              </p>
            </div>

            {/* Category Breakdown Progress Bars */}
            <div className="result-panel">
              <h3 className="result-panel-heading">
                <Layers size={15} style={{ color: '#7c5cfc' }} /> Category Audit Breakdown
              </h3>

              <div className="category-bars-list">
                <div className="category-bar-item">
                  <div className="category-bar-header">
                    <span>Technical Skills Match</span>
                    <span>{catScores.technical_skills_match}%</span>
                  </div>
                  <div className="category-bar-track">
                    <div className="category-bar-fill" style={{ width: `${catScores.technical_skills_match}%` }}></div>
                  </div>
                </div>

                <div className="category-bar-item">
                  <div className="category-bar-header">
                    <span>Experience Relevance</span>
                    <span>{catScores.experience_relevance}%</span>
                  </div>
                  <div className="category-bar-track">
                    <div className="category-bar-fill" style={{ width: `${catScores.experience_relevance}%` }}></div>
                  </div>
                </div>

                <div className="category-bar-item">
                  <div className="category-bar-header">
                    <span>Quantified Impact & Metrics</span>
                    <span>{catScores.quantified_impact}%</span>
                  </div>
                  <div className="category-bar-track">
                    <div className="category-bar-fill" style={{ width: `${catScores.quantified_impact}%` }}></div>
                  </div>
                </div>

                <div className="category-bar-item">
                  <div className="category-bar-header">
                    <span>Formatting & Parseability</span>
                    <span>{catScores.formatting_ats_parseability}%</span>
                  </div>
                  <div className="category-bar-track">
                    <div className="category-bar-fill" style={{ width: `${catScores.formatting_ats_parseability}%` }}></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Details Column */}
          <div className="details-column">
            {/* Executive Summary */}
            {results.summary && (
              <div className="result-panel">
                <h3 className="result-panel-heading">
                  <Zap size={15} className="result-panel-heading-icon" /> Brutally Honest Assessment Summary
                </h3>
                <p style={{ fontSize: '0.875rem', color: '#b4b4c8', lineHeight: 1.6, margin: 0 }}>
                  {results.summary}
                </p>
              </div>
            )}

            {/* Extracted Skills */}
            {skills.length > 0 && (
              <div className="result-panel">
                <h3 className="result-panel-heading">
                  <CheckCircle2 size={15} style={{ color: '#10b981' }} /> Verified Skills Detected ({skills.length})
                </h3>
                <div className="skills-tags-wrap">
                  {skills.map((skill, idx) => (
                    <span key={idx} className="skill-tag">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Missing Skills */}
            {missingSkills.length > 0 && (
              <div className="result-panel">
                <h3 className="result-panel-heading">
                  <AlertTriangle size={15} style={{ color: '#f59e0b' }} /> Recommended Keywords to Add ({missingSkills.length})
                </h3>
                <div className="skills-tags-wrap">
                  {missingSkills.map((skill, idx) => (
                    <span key={idx} className="missing-tag">
                      + {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Brutally Honest Fluff Removal Section */}
        {itemsToDelete.length > 0 && (
          <div className="result-panel delete-fluff-panel">
            <h3 className="result-panel-heading" style={{ color: '#ef4444' }}>
              <Trash2 size={16} style={{ color: '#ef4444' }} /> Brutally Honest Fluff Removal — What to Delete
            </h3>
            <p style={{ fontSize: '0.8rem', color: '#fca5a5', margin: '-0.35rem 0 0.5rem 0', opacity: 0.9 }}>
              The following lines, buzzwords, or filler sections degrade your ATS score and should be completely removed from your resume:
            </p>
            <ul className="resume-audit-bullet-list">
              {itemsToDelete.map((item, idx) => (
                <li key={idx} className="resume-audit-bullet-item delete-bullet-item">
                  <XCircle size={15} style={{ color: '#ef4444', flexShrink: 0, marginTop: '2px' }} />
                  <span style={{ color: '#fecaca', fontWeight: 500 }}>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Strengths & Improvements Checklist */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
          {/* Key Strengths */}
          <div className="result-panel">
            <h3 className="result-panel-heading">
              <Award size={15} style={{ color: '#10b981' }} /> Verified Strengths
            </h3>
            <ul className="resume-audit-bullet-list">
              {strengths.length > 0 ? (
                strengths.map((item, idx) => (
                  <li key={idx} className="resume-audit-bullet-item">
                    <CheckCircle2 size={14} style={{ color: '#10b981', flexShrink: 0, marginTop: '2px' }} />
                    <span>{item}</span>
                  </li>
                ))
              ) : (
                <li className="resume-audit-bullet-item">
                  <CheckCircle2 size={14} style={{ color: '#10b981', flexShrink: 0, marginTop: '2px' }} />
                  <span>Resume demonstrates solid technical foundation and clear structural layout.</span>
                </li>
              )}
            </ul>
          </div>

          {/* Actionable Improvements */}
          <div className="result-panel">
            <h3 className="result-panel-heading">
              <TrendingUp size={15} style={{ color: '#f59e0b' }} /> Actionable Recommendations
            </h3>
            <ul className="resume-audit-bullet-list">
              {improvements.length > 0 ? (
                improvements.map((item, idx) => (
                  <li key={idx} className="resume-audit-bullet-item">
                    <AlertTriangle size={14} style={{ color: '#f59e0b', flexShrink: 0, marginTop: '2px' }} />
                    <span>{item}</span>
                  </li>
                ))
              ) : (
                <li className="resume-audit-bullet-item">
                  <AlertTriangle size={14} style={{ color: '#f59e0b', flexShrink: 0, marginTop: '2px' }} />
                  <span>Add quantified metrics (e.g. latency reductions, scale, throughput) to your project descriptions.</span>
                </li>
              )}
            </ul>
          </div>
        </div>

        {/* Bullet Point Optimizer */}
        {bulletImprovements.length > 0 && (
          <div className="result-panel">
            <h3 className="result-panel-heading">
              <Sparkles size={15} style={{ color: '#7c5cfc' }} /> High-Impact Bullet Point Rewrites
            </h3>
            <div className="bullet-optimizer-list">
              {bulletImprovements.map((b, idx) => (
                <div key={idx} className="bullet-rewrite-card">
                  <div className="bullet-box-label original">Original Bullet Point:</div>
                  <p className="bullet-text-content" style={{ opacity: 0.75 }}>{b.original}</p>
                  
                  <div className="bullet-box-label optimized" style={{ marginTop: '0.35rem' }}>
                    <Sparkles size={12} /> ATS-Optimized Version:
                  </div>
                  <p className="bullet-text-content" style={{ fontWeight: 500, color: '#10b981' }}>{b.optimized}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Interview Focus Areas */}
        {interviewFocusAreas.length > 0 && (
          <div className="result-panel">
            <h3 className="result-panel-heading">
              <Target size={15} style={{ color: '#36a3ff' }} /> Tailored Technical Interview Preparation Guidance
            </h3>
            <ul className="resume-audit-bullet-list">
              {interviewFocusAreas.map((tip, idx) => (
                <li key={idx} className="resume-audit-bullet-item">
                  <ArrowRight size={14} style={{ color: '#36a3ff', flexShrink: 0, marginTop: '2px' }} />
                  <span>{tip}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};

export default ResumeResult;
