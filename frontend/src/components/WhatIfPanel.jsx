import { useState } from "react";
import TrajectoryCard from "./TrajectoryCard";

export default function WhatIfPanel({ baseline, whatifResult, onRun, loading }) {
  const [capWeight, setCapWeight] = useState(0.5);
  const [internshipWeight, setInternshipWeight] = useState(0.5);

  return (
    <div>
      <div className="card whatif-controls">
        <h3>What if...?</h3>
        <label>
          Weight on CAP: {capWeight.toFixed(1)}
          <input type="range" min="0" max="1" step="0.1" value={capWeight}
                 onChange={(e) => setCapWeight(Number(e.target.value))} />
        </label>
        <label>
          Weight on internships: {internshipWeight.toFixed(1)}
          <input type="range" min="0" max="1" step="0.1" value={internshipWeight}
                 onChange={(e) => setInternshipWeight(Number(e.target.value))} />
        </label>
        <button
          onClick={() => onRun({ cap_weight: capWeight, internship_weight: internshipWeight })}
          disabled={loading}
        >
          {loading ? "Re-planning..." : "Re-plan with these constraints"}
        </button>
      </div>

      {(baseline.length > 0 || whatifResult.length > 0) && (
        <div className="whatif-compare">
          <div className="whatif-column">
            <h4>Baseline</h4>
            {baseline.map((p, i) => <TrajectoryCard key={i} path={p} />)}
          </div>
          <div className="whatif-column">
            <h4>What-if</h4>
            {whatifResult.length === 0 && <p className="hint">Run a what-if to compare.</p>}
            {whatifResult.map((p, i) => <TrajectoryCard key={i} path={p} />)}
          </div>
        </div>
      )}
    </div>
  );
}
