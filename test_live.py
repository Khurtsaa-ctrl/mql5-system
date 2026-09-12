from job_finder import fetch_jobs, score_job, rank

jobs = [score_job(j) for j in fetch_jobs()]
print(f"\nНийт {len(jobs)} ажил олдлоо\n")

for j in rank(jobs)[:15]:
    apps = j['applications_count'] if j['applications_count'] is not None else '?'
    print(f"[{j['decision']:5s}] {str(apps):>3} өргөдөл  {j['age_hours']:>5.1f}ц  "
          f"${j['budget_min']}  {j['title'][:45]}")
    print(f"        {j['decision_reason']}")