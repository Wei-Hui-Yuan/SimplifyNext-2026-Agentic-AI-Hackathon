const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${path}: ${body}`);
  }
  return res.json();
}

export const api = {
  createStudent: (student) =>
    request("/students", { method: "POST", body: JSON.stringify(student) }),

  getStudent: (studentId) => request(`/students/${studentId}`),

  createTrajectories: (studentId) =>
    request(`/students/${studentId}/trajectories`, { method: "POST" }),

  createLeverageMoves: (studentId) =>
    request(`/students/${studentId}/leverage-moves`, { method: "POST" }),

  createOutreach: (studentId, targetType, targetId) =>
    request(`/students/${studentId}/outreach`, {
      method: "POST",
      body: JSON.stringify({ target_type: targetType, target_id: targetId }),
    }),

  approveOutreach: (draftId, decision) =>
    request(`/outreach/${draftId}/approve`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),

  createWhatIf: (studentId, weightOverrides) =>
    request(`/students/${studentId}/whatif`, {
      method: "POST",
      body: JSON.stringify({ weight_overrides: weightOverrides }),
    }),

  createCheckpoint: (studentId) =>
    request(`/students/${studentId}/checkpoint`, { method: "POST" }),

  logAction: (studentId, actionType, refId, detail) =>
    request(`/students/${studentId}/actions`, {
      method: "POST",
      body: JSON.stringify({ action_type: actionType, ref_id: refId, detail }),
    }),
};
