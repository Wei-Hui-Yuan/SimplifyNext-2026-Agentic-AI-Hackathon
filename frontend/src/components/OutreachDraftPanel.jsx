export default function OutreachDraftPanel({ draft, onApprove }) {
  if (!draft) return null;

  return (
    <div className="card outreach-panel">
      <h3>Review & send</h3>
      <p className="hint">Compass never sends anything itself — this is a draft only. Approving marks it ready to send yourself.</p>
      <div className="draft-body">
        <div className="field">
          <span className="label">Subject</span>
          <div className="subject">{draft.subject}</div>
        </div>
        <div className="field">
          <span className="label">Body</span>
          <pre className="body">{draft.body}</pre>
        </div>
      </div>
      <div className="status-row">
        <span className={`status-badge status-${draft.status}`}>{draft.status}</span>
        {draft.status === "draft" && (
          <div className="actions">
            <button onClick={() => onApprove(draft.draft_id, "approved")}>Approve</button>
            <button className="secondary" onClick={() => onApprove(draft.draft_id, "rejected")}>Reject</button>
          </div>
        )}
      </div>
    </div>
  );
}
