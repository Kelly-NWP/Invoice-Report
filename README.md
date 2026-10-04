# Jobs & invoice status report

## Deploy (about 10 minutes)
1. Create a **private** GitHub repo and upload these files (app.py, requirements.txt, render.yaml, README.md).
2. In Render: New > Web Service > connect the repo. Build: `pip install -r requirements.txt`. Start: `gunicorn app:app --timeout 120`.
3. Add two environment variables in Render:
   - `HCP_API_KEY` = your key (Housecall Pro > App Store > API Key Management)
   - `APP_PASSWORD` = a password you and your boss will share
4. Open the Render URL. Log in with any username and that password.

## First run
Open `/check` to see one raw job and invoice. If amounts or statuses look wrong, send me that output
(remove customer names first) and I'll adjust field names. If amounts look 100x too big/small,
set `AMOUNTS_IN_CENTS` to `false` in Render.
