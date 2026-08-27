export default function CheckpointView({ checkpoint, onSimulate, loading }) {
  return (
    <div>
      <div className="card checkpoint-controls">
        <h3>Simulate two weeks passing</h3>
        <p className="hint">
          Logs a few realistic actions (outreach sent, a competition joined, a module started),
          then re-checks how well your progress lines up with the baseline trajectories.
        </p>
        <button onClick={onSimulate} disabled={loading}>
          {loading ? "Checking..." : "Simulate & checkpoint"}
        </button>
      </div>

      {checkpoint && (
        <div className="card checkpoint-result">
          <h4>Alignment since baseline</h4>
          <div className="alignment-bars">
            {Object.entries(checkpoint.alignment_delta || {}).map(([name, score]) => (
              <div key={name} className="alignment-row">
                <span className="path-name">{name}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${Math.min(score * 100, 100)}%` }} />
                </div>
                <span className="score">{(score * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>

          <h4>Actions since baseline</h4>
          <ul className="action-timeline">
            {(checkpoint.actions_since_baseline || []).map((a, i) => (
              <li key={i}>
                <span className="action-type">{a.action_type}</span>
                {a.detail?.note && <span className="action-note"> — {a.detail.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
