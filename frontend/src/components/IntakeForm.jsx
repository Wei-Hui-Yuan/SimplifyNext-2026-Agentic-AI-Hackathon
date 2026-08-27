import { useState } from "react";

const DEFAULTS = {
  student_id: "demo_001",
  name: "Alex Tan",
  year: 1,
  cap: 4.3,
  modules_taken: "CS1101S, CS1231S, MA1521",
  interests: "machine learning, natural language processing, AI safety",
  goal: "I think I want to work in AI, but I'm not sure whether I want to do research or industry.",
};

export default function IntakeForm({ onSubmit, loading }) {
  const [form, setForm] = useState(DEFAULTS);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    onSubmit({
      student_id: form.student_id,
      name: form.name,
      year: Number(form.year),
      cap: Number(form.cap),
      modules_taken: form.modules_taken.split(",").map((s) => s.trim()).filter(Boolean),
      interests: form.interests.split(",").map((s) => s.trim()).filter(Boolean),
      goal: form.goal,
    });
  }

  return (
    <form className="card intake-form" onSubmit={handleSubmit}>
      <h2>Tell Compass what you want to achieve</h2>

      <label>
        Student ID
        <input value={form.student_id} onChange={(e) => update("student_id", e.target.value)} required />
      </label>

      <div className="form-row">
        <label>
          Name
          <input value={form.name} onChange={(e) => update("name", e.target.value)} required />
        </label>
        <label>
          Year
          <input type="number" min="1" max="5" value={form.year} onChange={(e) => update("year", e.target.value)} required />
        </label>
        <label>
          CAP
          <input type="number" step="0.01" min="0" max="5" value={form.cap} onChange={(e) => update("cap", e.target.value)} required />
        </label>
      </div>

      <label>
        Modules taken (comma-separated)
        <input value={form.modules_taken} onChange={(e) => update("modules_taken", e.target.value)} />
      </label>

      <label>
        Interests (comma-separated)
        <input value={form.interests} onChange={(e) => update("interests", e.target.value)} />
      </label>

      <label>
        Where do you want to be in 3 years?
        <textarea rows={3} value={form.goal} onChange={(e) => update("goal", e.target.value)} required />
      </label>

      <button type="submit" disabled={loading}>
        {loading ? "Thinking..." : "Generate my trajectories"}
      </button>
    </form>
  );
}
