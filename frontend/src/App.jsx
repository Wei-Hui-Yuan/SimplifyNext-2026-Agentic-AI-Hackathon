import { useState } from "react";
import "./App.css";
import { api } from "./api";
import IntakeForm from "./components/IntakeForm";
import TrajectoryCard from "./components/TrajectoryCard";
import LeverageMoveCard from "./components/LeverageMoveCard";
import OutreachDraftPanel from "./components/OutreachDraftPanel";
import WhatIfPanel from "./components/WhatIfPanel";
import CheckpointView from "./components/CheckpointView";

const TABS = [
  { id: "intake", label: "Intake" },
  { id: "moves", label: "Trajectories & Moves" },
  { id: "outreach", label: "Outreach" },
  { id: "whatif", label: "What-if" },
  { id: "checkpoint", label: "Checkpoint" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("intake");
  const [studentId, setStudentId] = useState(null);
  const [trajectories, setTrajectories] = useState([]);
  const [leverageMoves, setLeverageMoves] = useState([]);
  const [outreachDraft, setOutreachDraft] = useState(null);
  const [whatifTrajectories, setWhatifTrajectories] = useState([]);
  const [checkpoint, setCheckpoint] = useState(null);
  const [loading, setLoading] = useState(null);
  const [error, setError] = useState(null);

  async function withLoading(key, fn) {
    setError(null);
    setLoading(key);
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(null);
    }
  }

  function handleIntakeSubmit(profile) {
    withLoading("intake", async () => {
      await api.createStudent(profile);
      setStudentId(profile.student_id);
      const t = await api.createTrajectories(profile.student_id);
      setTrajectories(t.trajectories);
      const m = await api.createLeverageMoves(profile.student_id);
      setLeverageMoves(m.leverage_moves);
      setActiveTab("moves");
    });
  }

  function handleDraftOutreach(move) {
    withLoading("outreach", async () => {
      const targetType = move.ref_id.startsWith("prof_") ? "professor" : "opportunity";
      const result = await api.createOutreach(studentId, targetType, move.ref_id);
      setOutreachDraft(result.outreach_draft);
      setActiveTab("outreach");
    });
  }

  function handleApprove(draftId, decision) {
    withLoading("approve", async () => {
      const updated = await api.approveOutreach(draftId, decision);
      setOutreachDraft(updated);
    });
  }

  function handleWhatIf(weightOverrides) {
    withLoading("whatif", async () => {
      const result = await api.createWhatIf(studentId, weightOverrides);
      setWhatifTrajectories(result.trajectories);
    });
  }

  function handleSimulateCheckpoint() {
    withLoading("checkpoint", async () => {
      await api.logAction(studentId, "outreach_sent", outreachDraft?.target_id ?? "", { note: "sent the approved draft" });
      await api.logAction(studentId, "competition_joined", "comp_nus_ai_hackathon", { note: "joined the AI hackathon" });
      await api.logAction(studentId, "manual_note", "", { note: "started a new module this semester" });
      const result = await api.createCheckpoint(studentId);
      setCheckpoint(result);
    });
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>NUS Compass</h1>
        <p className="tagline">Plans, acts, and adapts as your goals and the opportunities around you change.</p>
      </header>

      <nav className="tab-bar">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab ${activeTab === t.id ? "active" : ""}`}
            onClick={() => setActiveTab(t.id)}
            disabled={t.id !== "intake" && !studentId}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {error && <div className="error-banner">{error}</div>}

      <main className="tab-content">
        {activeTab === "intake" && (
          <IntakeForm onSubmit={handleIntakeSubmit} loading={loading === "intake"} />
        )}

        {activeTab === "moves" && (
          <div>
            <section>
              <h2>Your trajectory paths</h2>
              <div className="trajectory-grid">
                {trajectories.map((p, i) => <TrajectoryCard key={i} path={p} />)}
              </div>
            </section>
            <section>
              <h2>This semester's highest-leverage moves</h2>
              <div className="move-list">
                {leverageMoves.map((m, i) => (
                  <LeverageMoveCard key={i} move={m} onDraftOutreach={handleDraftOutreach} />
                ))}
              </div>
            </section>
          </div>
        )}

        {activeTab === "outreach" && (
          outreachDraft
            ? <OutreachDraftPanel draft={outreachDraft} onApprove={handleApprove} />
            : <p className="hint">Draft an outreach message from a move on the Trajectories & Moves tab first.</p>
        )}

        {activeTab === "whatif" && (
          <WhatIfPanel
            baseline={trajectories}
            whatifResult={whatifTrajectories}
            onRun={handleWhatIf}
            loading={loading === "whatif"}
          />
        )}

        {activeTab === "checkpoint" && (
          <CheckpointView
            checkpoint={checkpoint}
            onSimulate={handleSimulateCheckpoint}
            loading={loading === "checkpoint"}
          />
        )}
      </main>
    </div>
  );
}
