# 📊 InsightBoard

> **Drop a CSV. Get a dashboard.**

InsightBoard turns any sales CSV into an interactive dashboard with KPIs and
charts — automatically. No configuration, no SQL, no spreadsheet gymnastics.

![screenshot](docs/screenshot.png)

## ✨ Features

- 📁 Upload any `.csv` file (UTF-8, Latin-1, CP1252 supported)
- 🧠 **Automatic schema detection** (date, amount, quantity, product, city)
- 📈 KPIs: total revenue, average order, total quantity, top product, top city
- 📊 Interactive charts: revenue by city, top products, revenue over time
- 🎨 Clean responsive UI (Django templates + Plotly)
- 🐳 Fully dockerized
- ✅ Tested with pytest-django

## 🚀 Quick start (Docker)

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000) and upload `data/sample_sales.csv`.

## 🚀 Quick start (local, no Docker)

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## 🧪 Tests

```bash
docker compose run --rm web pytest -q
```

## 🗂️ Project structure

```
InsightBoard/
├── InsightApp/
│   ├── admin.py            # Analysis admin
│   ├── forms.py            # UploadCSVForm
│   ├── models.py           # Analysis model
│   ├── services/
│   │   ├── csv_loader.py   # load + schema detection
│   │   ├── analyzer.py     # KPIs + aggregations
│   │   └── charts.py       # Plotly rendering
│   ├── urls.py
│   └── views.py
├── ProjectInsight/         # Django settings
├── templates/              # base, index, dashboard
├── static/css/style.css
├── data/sample_sales.csv
├── Dockerfile
└── docker-compose.yml
```

## 🐳 Docker

Build and run:

```bash
docker build -t insightboard .
docker run -p 8000:8000 insightboard
```

## ☁️ Deployment (Render)

1. Push the repo to GitHub.
2. Render → **New Web Service** → connect the repo.
3. Render detects the `Dockerfile` automatically.
4. Set the healthcheck path to `/` (or add a `/health/` view).
5. Deploy. Add an UptimeRobot ping every 5 min to avoid cold starts.

## 🛠️ Stack

`Python 3.12` · `Django 5` · `Pandas` · `Plotly` · `Docker` · `WhiteNoise`

## 📄 License

MIT# InsightBoard
