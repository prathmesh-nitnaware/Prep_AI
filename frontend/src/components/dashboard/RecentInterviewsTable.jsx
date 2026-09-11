import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { History, Trash2, ArrowUpRight, Inbox, Eye } from 'lucide-react';
import { getScoreBadge } from '../../utils/dashboardMetrics';

export const RecentInterviewsTable = ({ history, onDelete }) => {
  const navigate = useNavigate();

  const handleRowClick = (session) => {
    const sId = session.id || session._id || session.session_id;
    navigate(sId ? `/interview/report/${sId}` : '/interview/report', {
      state: {
        session_id: sId,
        history: session.answers || [],
        config: session,
      },
    });
  };

  return (
    <div className="dash-panel-card recent-interviews-panel">
      <div className="dash-panel-header">
        <div className="dash-panel-title-wrap">
          <History size={18} className="dash-panel-icon" />
          <h3 className="dash-panel-title">Recent Mock Interviews</h3>
        </div>
        {history.length > 0 && (
          <span className="dash-panel-meta-text">
            Showing {Math.min(5, history.length)} of {history.length}
          </span>
        )}
      </div>

      {history && history.length > 0 ? (
        <div className="interviews-table-wrap">
          <table className="interviews-table">
            <thead>
              <tr>
                <th>Target Role</th>
                <th>Experience / Focus</th>
                <th>Score</th>
                <th>Date</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {history.slice(0, 5).map((session) => {
                const score = session.overall_score || 0;
                const badge = getScoreBadge(score);
                const role = session.role || 'Software Engineer';
                const exp = session.experience || 'Entry Level';
                const dateStr = session.created_at
                  ? new Date(session.created_at).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                    })
                  : 'Recent';

                return (
                  <tr
                    key={session.id || session._id}
                    className="interview-table-row"
                    onClick={() => handleRowClick(session)}
                  >
                    <td className="col-role">
                      <div className="role-main-text">{role}</div>
                      <div className="role-sub-text">
                        {session.difficulty || 'Standard'} Difficulty
                      </div>
                    </td>

                    <td className="col-meta">
                      <span className="exp-text">{exp}</span>
                    </td>

                    <td className="col-score">
                      <div className="score-cell-wrap">
                        <span className="score-number">{score}%</span>
                        <span className={`score-badge ${badge.color}`}>
                          {badge.label}
                        </span>
                      </div>
                    </td>

                    <td className="col-date">
                      <span className="date-text">{dateStr}</span>
                    </td>

                    <td className="col-actions" style={{ textAlign: 'right' }}>
                      <div className="table-action-buttons">
                        <button
                          className="btn-table-action"
                          title="View Evaluation Report"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRowClick(session);
                          }}
                        >
                          <Eye size={15} />
                        </button>
                        <button
                          className="btn-table-action btn-del"
                          title="Delete Record"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDelete(e, session.id || session._id);
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="interviews-empty-state">
          <Inbox size={32} className="empty-state-icon" />
          <h4 className="empty-state-title">No mock interviews recorded yet</h4>
          <p className="empty-state-text">
            Start a 5-stage simulation to practice fundamentals, system design, and behavioral questions.
          </p>
          <Link to="/interview/setup" className="btn-dash-primary" style={{ marginTop: '1rem' }}>
            <span>Start First Interview</span>
          </Link>
        </div>
      )}
    </div>
  );
};

export default RecentInterviewsTable;
