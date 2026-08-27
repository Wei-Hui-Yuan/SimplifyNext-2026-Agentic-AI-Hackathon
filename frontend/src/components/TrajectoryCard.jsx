export default function TrajectoryCard({ path }) {
  return (
    <div className="card trajectory-card">
      <h3>{path.name}</h3>
      <p className="rationale">{path.rationale}</p>
      <ol className="steps">
        {path.steps.map((step, i) => (
          <li key={i}>{step}</li>
        ))}
      </ol>
      {path.likely_outcomes?.length > 0 && (
        <div className="outcomes">
          <span className="label">Likely outcomes</span>
          <ul>
            {path.likely_outcomes.map((o, i) => (
              <li key={i}>{o}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
