# Synthetic data

Everything in this folder is fictional — invented professor personas, invented
companies, invented alumni — same convention as `lab/sample_docs/expenses.pdf`
(fictional staff, fictional amounts, fictional company). No real NUS staff,
students, or companies are named or described anywhere here.

Research areas are deliberately realistic (they mirror real NUS School of
Computing-style groupings — AI/ML, systems, HCI, theory, vision — so matching
against a student's interests behaves sensibly), but every name, lab, and
"previously supervised" claim is made up.

Each file is a flat JSON list. Every record's `id` is referenced by
`app/tools.py`/`app/graph.py` and by `outreach_drafts.target_id` in Supabase —
keep ids stable once other code depends on them.
