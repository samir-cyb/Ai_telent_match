# System repair plan

Maintain the existing Django apps, student/company/admin roles, profile review
and Save step, optional vetting, ranking and hire/reject feedback workflow.
Keep matching formulas, eligibility threshold, grading weights, pipeline final
weights and Q-learning calculations unchanged.

1. Establish a branch on the current main; preserve existing student UI.
2. Fix API signatures, session identity, ownership, CSRF and input validation.
3. Make profile updates atomic; report CV failures explicitly; import GitHub
   projects using stable repository identity without deleting manual entries.
4. Repair assessment refresh/timers; hide quiz solutions; use the existing
   Judge0 sandbox for every coding language. Preserve grading transactions.
5. Add database uniqueness and locks around applications, points and pipeline
   stages. Preserve existing data and stop migrations on conflicting records.
6. Restore optional chat storage/routing and remove exposed credentials and
   unsafe HTML sinks. Configure production settings through the environment.
7. Provide clean dependencies, fresh/upgrade tests, CI and Windows/Linux setup.
8. Record tested results and owner-side configuration requirements; publish
   a reviewable Git branch and provide a downloadable handoff if remote writes
   are unavailable.

No production database, uploaded user CV, live AI billing, SMTP account or
deployment will be changed during repair validation.
