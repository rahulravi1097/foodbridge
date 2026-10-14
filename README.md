# FoodBridge — Food Surplus Donation Platform

A Flask web application prototype supporting **SDG 2 (Zero Hunger)** and **SDG 12 (Responsible Consumption and Production)**. Donors can publish surplus food, approved NGOs/volunteers can claim it, and the donation lifecycle is tracked through pickup and delivery.

## Features

- Role-based accounts: donor, NGO/volunteer, administrator
- Secure password hashing and Flask-Login sessions
- NGO/volunteer approval by administrator
- Create, edit, cancel and browse food listings
- City and food-category filters
- Expiry checks and status workflow: `available → claimed → picked_up → delivered`
- Claim ownership checks and one claim per donation
- Admin dashboard with counts and status breakdown
- Feedback after delivery
- CSRF protection on Flask-WTF forms
- SQLite for local quick start; MySQL support through `DATABASE_URL`
- Render-compatible `Procfile` and `render.yaml`

## Local setup (Windows / VS Code)

1. Install Python 3.11 or newer.
2. Open the `FoodBridge` folder in VS Code.
3. In PowerShell, run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. Set a long random `SECRET_KEY` and a strong `ADMIN_PASSWORD` as environment variables if you want to bootstrap an administrator. The app uses SQLite by default for local development.
5. Run `python app.py` and open http://127.0.0.1:5000.

## Create an admin account

Set `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` before the first run. Optional variables are `ADMIN_NAME` and `ADMIN_CITY`. The app creates the administrator only if those variables are set and the email does not already exist. Do not use example credentials on a public deployment.

## MySQL / DBeaver

Create a database, for example:

```sql
CREATE DATABASE foodbridge_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Set `DATABASE_URL` to `mysql+pymysql://USERNAME:PASSWORD@HOST:3306/foodbridge_db?charset=utf8mb4`. URL-encode special characters in the password. Restrict database network access and do not expose port 3306 to all IPs.

## Deploy to Render

1. Create a Web Service from this GitHub repository.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app`
4. Configure `SECRET_KEY`, `DATABASE_URL`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` in Render's environment settings. Optional: `ADMIN_NAME`, `ADMIN_CITY`.
5. Deploy and test the generated URL.

A local SQLite file may not persist across some hosting deployments. Use a managed persistent database for production. This app supports MySQL connection strings; verify that your selected database provider is reachable from Render.

## Security and production checklist

- Use a unique random `SECRET_KEY` and strong admin password.
- Use HTTPS and a least-privilege database user.
- Never commit `.env`, database passwords, or production secrets.
- Test role restrictions, NGO approval, claim collisions, expired listings, and status transitions with dummy data.
- FoodBridge is a coordination tool, not a food-safety certification service.
- Add database migrations before evolving a live production schema; `db.create_all()` does not alter existing tables.

## Core database entities

- `User`: profile, hashed password, role, approval
- `Donation`: food details, quantity/unit, deadline, pickup location, status
- `Claim`: claimant and lifecycle timestamps
- `Feedback`: rating and comment after delivery

## Current scope / limitations

- Pickup addresses are stored as text; map integration is not included.
- Notifications are not configured by default.
- Food quantity metrics use entered units; do not add quantities across unlike units as if equivalent.
- This is an internship-ready MVP and should be tested with dummy data before real-world use.
