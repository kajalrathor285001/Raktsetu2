# RaktSetu — Full-stack mobile-ready prototype

A Flask + SQLite educational demonstration app. The interface is responsive and can be opened from a phone browser after online deployment.

## Included
- Role-based registration and login (donor, patient, hospital, NGO)
- Blood request submission and request status workflow
- Donor request filtering by blood group and city
- Donor interest/response tracking
- Any registered hospital or admin can verify pending requests
- Patient cancellation and soft-archiving
- Request activity log
- CSRF token checks on POST forms
- NGO donation camp publishing and donor interest registration
- Admin overview
- Render deployment configuration in `render.yaml`

## Use from a phone — no VS Code required
Read `MOBILE_DEPLOY_GUIDE.md`. You will need a GitHub account and a Render account to publish the app and receive a live website URL. The ZIP itself is not a live website.

## Render settings
The included `render.yaml` configures Python, installs `requirements.txt`, starts `gunicorn app:app`, and generates a secret key.

## Important limitations
This is an educational prototype, not a production blood-bank system or emergency medical service. Do not enter real patient or donor data. Render's free filesystem is temporary, so SQLite data can be lost on restart, sleep or redeployment. Hospital identities are not independently verified. Matching by blood group and city is preliminary only; it does not establish clinical compatibility or donor eligibility. Qualified medical professionals must perform screening and cross-matching.
