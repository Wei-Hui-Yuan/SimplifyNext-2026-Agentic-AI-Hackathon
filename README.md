# 🧠 NUS Compass

An AI agent that optimizes a student's entire university trajectory — built for the SimplifyNext 2026 Agentic AI Hackathon.

**This isn't just a pitch — it's a working full-stack app.** FastAPI + LangGraph backend (5 linear graphs, one shared state), React frontend, real NUSMods module/prerequisite data (727 modules, live-fetched), Groq-hosted LLM for trajectory generation, leverage-move ranking, and outreach drafting.

- **Run it**: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — one command (`run_dev.py`) starts both servers; the only thing you need to supply is a free Groq API key.
- **How it's built**: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data pipeline, agent graphs, storage, endpoints.
- **What's real vs. synthetic**: the NUS module catalog and prerequisite graph are real, live NUSMods data; professors, internships, competitions, scholarships, and alumni stories are a small hand-authored synthetic dataset (see [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md#whats-real-vs-synthetic)) — no real people or companies.

The rest of this document is the original product vision this build was scoped from.

---

The core insight

An NUS student's biggest problem isn't lack of information.

It's that the important information is fragmented across hundreds of places, and the opportunities are highly interconnected.

A student might have:

a CAP they're trying to maintain
graduation requirements
module prerequisites
SEP opportunities
internships
research positions
hackathons
competitions
scholarships
CCAs
professors they should meet
networking opportunities
friends who know about opportunities
career goals they aren't even sure about

And the student is expected to manually figure out how all these pieces fit together.

NUS Compass becomes the intelligence layer over all of that.

The crazy part: build a model of the student's future

Instead of:

“What do you want to do?”

You ask:

“Where do you want to be in 3 years, and what would make that outcome more likely?”

Suppose a Year 1 NUS student says:

“I think I want to work in AI, but I'm not sure whether I want to do research or industry.”

Compass constructs possible trajectories:

Path A — AI Engineer
→ modules
→ projects
→ internships
→ technical skills
→ GitHub portfolio
→ interview preparation

Path B — AI Research
→ specific professors
→ research assistant opportunities
→ research modules
→ reading groups
→ publications
→ graduate school options

Path C — AI + Entrepreneurship
→ NUS entrepreneurship programmes
→ startup competitions
→ technical cofounders
→ incubators
→ funding opportunities

Then it continuously watches reality and says:

“Based on what you've actually done this semester, Path B now looks substantially more aligned with you than Path A.”

That's the adaptation component.

But here's where it gets REALLY interesting
Build a university opportunity graph.

Imagine every relevant thing at NUS as a node:

Student

↕️

Module

↕️

Professor

↕️

Research Lab

↕️

Internship

↕️

Alumni

↕️

Company

↕️

Competition

↕️

CCA

↕️

Scholarship

↕️

Programme

And relationships between them.

For example:

CS2103 → teaches skills → useful for → SWE internships

Professor X → researches → LLMs

Professor X → previously supervised → student Y

Student Y → interned at → Company Z

Company Z → recruits heavily from → NUS students with → certain skills

Suddenly you're not building a chatbot.

You're building a decision engine for navigating university.

And the agent doesn't just recommend things.

This is critical.

It acts.

Imagine the agent notices:

“You told me you want to pursue AI research. Professor X has just posted an RA opportunity. You already took the relevant module and your project is closely related.”

Instead of sending you a notification:

Opportunity found.

It does:

I've checked the requirements. You qualify.
I've drafted an email to Professor X using your project experience.
I've updated your research timeline.
The application closes Friday.
Review & send?

You approve.

It sends.

Then it tracks the outcome.

If rejected:

“Professor X isn't taking students this semester. Two other labs have openings that match your profile. I've ranked them based on fit.”

That's an agent.

The killer feature: “What should I do this semester?”

Every semester, Compass gives you a small number of high-leverage actions.

Not 47 tasks.

Something like:

Your highest-leverage moves this month

1. Talk to Prof. Tan

You have an 87% skill/profile match with his research.

2. Apply for X

Deadline: 14 days.

Your probability of being competitive is high because you've completed X modules.

3. Build this project

You're missing one portfolio signal for the internship path you're targeting.

4. Don't take this module

It conflicts with your longer-term plan and creates unnecessary workload.

5. Meet this person

An NUS alumnus with a career trajectory similar to the one you're exploring is speaking at an event next week.

The product becomes:

“If I were you, what would I do next?”

The most big-brained feature: counterfactual simulation

Let students ask:

“What happens if I take these modules?”

or:

“What if I prioritize CAP over internships?”

or:

“What if I want to go to Stanford for grad school?”

or:

“What should I do differently if I want a $200k+ tech career?”

The system generates different trajectories.

Example

Current trajectory

CAP: 4.2
2 internships
No research
Moderate portfolio

→ likely outcomes X/Y/Z

Research-heavy trajectory

CAP: 4.0
1 internship
RA with Professor X
research project
paper

→ stronger trajectory toward graduate research

Industry-heavy trajectory

CAP: 4.0
2 internships
3 strong projects
competitive interview preparation

→ stronger trajectory toward industry

Now the student can make decisions based on consequences rather than vibes.

And it should understand that students have limited resources

This is where the system becomes genuinely useful.

Every student has constraints:

Time
Energy
Money
CAP
Social bandwidth
Attention

So Compass shouldn't optimize:

“Maximum opportunities.”

It should optimize:

“Maximum long-term outcome given this student's actual constraints.”

For example:

“You are considering joining three CCAs, doing an RA position and taking 24 MCs.”

The system might say:

Don't.

Not because those things are bad, but because your predicted workload makes it highly likely that your CAP and sleep will deteriorate, which undermines the objective you're actually trying to achieve.

That's a much more interesting product philosophy.

The ultimate version

Eventually, every student gets a University Digital Twin.

Not a creepy surveillance profile.

A personal model containing:

Where you are
Skills
Academic progress
Experience
Interests
Network
Projects
Goals
Where you could go
Careers
Graduate school
Entrepreneurship
Research
Fellowships
Different industries
What's changing around you
New internships
Professor openings
Scholarships
Competitions
Events
Recruitment cycles
Module availability
What should happen next

And the agent continuously closes the gap between:

Current Student → Desired Future

Why NUS is an unusually good starting point

You don't need to solve the entire world.

You can make the first version hyper-specific to NUS.

That gives you a constrained environment with:

a relatively defined student population
structured academic requirements
huge amounts of institutional information
recurring academic cycles
clubs and organisations
career services
research opportunities
alumni
employers
exchange programmes
scholarships
competitions

And, importantly, students constantly make decisions with long-term consequences without having enough context to make them.

That's your wedge.

The one-sentence pitch

NUS Compass is an AI agent that builds a model of where an NUS student wants to go, understands the university ecosystem, and continuously plans and takes actions to get them there—adapting as their goals, opportunities and circumstances change.

Or, punchier:

“Google Maps for your NUS life—but it doesn't just tell you the route. It drives.”

If I were actually building this

I'd not start with the giant vision.

I'd build one magical workflow:

“Tell me what you want to achieve by graduation.”

Then Compass produces:

Your 4-year trajectory → this semester's priorities → this week's actions → actions it can execute for you.
