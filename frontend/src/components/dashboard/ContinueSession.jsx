import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Play, ArrowRight, CheckCircle2, Clock } from 'lucide-react';
import { formatTimeAgo } from '../../utils/dashboardMetrics';

export const ContinueSession = ({ latestSession, totalInterviews }) => {
  const navigate = useNavigate();

  if (!latestSession || totalInterviews === 0) {
    return (
      <div className="dash-continue-card empty-track">
        <div className="continue-left">
          <div className="continue-badge">Ready to Practice?</div>
          <h3 className="continue-title">Start Your Technical Placement Track</h3>
          <p className="continue-desc">
            Practice 5-stage adaptive technical and behavioral interviews tailored to your target engineering role.
          </p>
        </div>
        <div className="continue-right">
          <Link to="/interview/setup" className="btn-dash-primary">
            <Play size={16} fill="currentColor" />
            <span>Launch Interview</span>
          </Link>
        </div>
      </div>
    );
  }

  const roleName = latestSession.role || 'Engineering Candidate';
  const stageName = latestSession.status === 'completed' ? 'Completed (5 / 5 Stages)' : 'Active Session';
  const score = latestSession.overall_score || 0;
  const timeAgo = formatTimeAgo(latestSession.created_at);

  const handleReview = () => {
    const sId = latestSession.id || latestSession._id || latestSession.session_id;
    navigate(sId ? `/interview/report/${sId}` : '/interview/report', {
      state: {
        session_id: sId,
        history: latestSession.answers || [],
        config: latestSession,
      },
    });
  };

  return (
    <div className="dash-continue-card active-track">
      <div className="continue-left">
        <div className="continue-meta-row">
          <span className="continue-badge">Latest Track</span>
          {timeAgo && (
            <span className="continue-time">
              <Clock size={13} />
              {timeAgo}
            </span>
          )}
        </div>

        <h3 className="continue-title">{roleName}</h3>
        
        <div className="continue-stage-row">
          <span className="stage-label">Status:</span>
          <span className="stage-val">{stageName}</span>
          {score > 0 && (
            <>
              <span className="stage-sep">•</span>
              <span className="stage-label">Overall Score:</span>
              <span className="stage-val score-highlight">{score}%</span>
            </>
          )}
        </div>
      </div>

      <div className="continue-right">
        <button onClick={handleReview} className="btn-dash-secondary">
          <span>Review Report</span>
          <ArrowRight size={15} />
        </button>
        <Link to="/interview/setup" className="btn-dash-primary">
          <Play size={15} fill="currentColor" />
          <span>New Session</span>
        </Link>
      </div>
    </div>
  );
};

export default ContinueSession;
