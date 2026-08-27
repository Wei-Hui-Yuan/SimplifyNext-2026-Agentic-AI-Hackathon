const TYPE_LABEL = {
  module: "Take a module",
  meeting: "Meet someone",
  apply: "Apply",
  skip: "Don't do this",
  event: "Attend",
};

export default function LeverageMoveCard({ move, onDraftOutreach }) {
  const canDraft = (move.move_type === "apply" || move.move_type === "meeting") && move.ref_id;

  return (
    <div className={`card move-card move-${move.move_type}`}>
      <div className="move-header">
        <span className="move-type-badge">{TYPE_LABEL[move.move_type] || move.move_type}</span>
        {move.deadline && <span className="deadline">deadline: {move.deadline}</span>}
      </div>
      <h4>{move.title}</h4>
      <p className="why">{move.why}</p>
      {move.confidence_note && <p className="confidence">{move.confidence_note}</p>}
      {canDraft && (
        <button className="secondary" onClick={() => onDraftOutreach(move)}>
          Draft outreach
        </button>
      )}
    </div>
  );
}
