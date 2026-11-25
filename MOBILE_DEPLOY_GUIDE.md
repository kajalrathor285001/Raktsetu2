# RaktSetu — use it from your phone

This package is prepared for mobile browser use and one-click-style deployment through Render. You do **not** need VS Code or Python on your phone.

## Important: a live website link is created only after deployment

A ZIP file by itself cannot become a public website. To get your own `https://...onrender.com` link, the project must be placed in a GitHub repository and connected to a Render account. The repository and hosting accounts must belong to you; this package does not contain your passwords or account access.

## Browser-only deployment (phone or computer)

1. Sign in to GitHub in your browser and create a **new private repository** named `raktsetu-demo`.
2. Extract this ZIP on a computer, or use a file manager that can extract ZIP files.
3. Open the new GitHub repository, choose **Add file → Upload files**, and upload the *contents* of the `RaktSetu_FullStack` folder (not the outer ZIP). Commit the upload.
4. Open https://render.com in your browser and sign in.
5. Choose **New → Blueprint**, connect GitHub, and select `raktsetu-demo`.
6. Render reads `render.yaml`, installs the requirements and starts the Flask app. Wait for deployment to finish.
7. Open the `onrender.com` URL Render provides. Save it on your phone's home screen if you want app-like access.

## Mobile support

The pages include a responsive layout, touch-friendly form controls, and horizontally scrollable tables on narrow screens. Open the deployed URL in Chrome or another mobile browser.

## Important demo limitations

- This is an educational prototype, not a real blood-bank or emergency service. Never enter real patient or donor information.
- The included SQLite database on Render's free web service uses temporary storage. Data may be lost when the service restarts, sleeps or is redeployed. Use dummy accounts and dummy requests only. A persistent database must be configured before relying on stored records.
- Hospital accounts are self-registered in this prototype; their identities are not independently verified. Do not treat a request's in-app verification as medical or institutional verification.
- Blood-group/city matching is only a preliminary search. It does not determine clinical compatibility or donor eligibility. Qualified medical professionals must handle screening and cross-matching.

## If you need to update the website

Upload the changed project files to the same GitHub repository. Render will redeploy automatically when connected to the repository. No VS Code is required.
