# RickshawParts Pro

A Flask + SQLite spare-parts storefront and shop administration MVP for Pakistan. Currency: PKR. Supports Petrol, CNG, Electric and All vehicle fitment categories.

## Included
- Public storefront, search, category and vehicle filters
- Product detail pages, cart and checkout (Cash on Delivery / manual payment record)
- Customer and order records
- Admin login, dashboard KPIs, product catalogue, stock adjustment and low-stock alerts
- Order and payment status updates, sales/profit summary, CSV product export
- SQLite database and health endpoint

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. Demo admin: `admin` / `Admin@12345`.

## Deployment (Render)
Use the included `render.yaml`. Set a strong `ADMIN_PASSWORD` and keep the generated `SECRET_KEY`. The persistent disk stores SQLite data at `/var/data/rickshawparts.db`.

## Important production notes
This is a working MVP, not a payment-certified production platform. Checkout records orders and payment method; it does not charge cards or mobile wallets. Before serving real customers, add HTTPS/domain, strong secrets, rate limiting/CSRF protection, backups, PostgreSQL for multi-user scale, payment gateway integration, supplier purchasing, staff roles, audit logs and verified product fitment/price data. Demo products/prices/stock are sample data. Do not use the demo admin password on a public deployment.
