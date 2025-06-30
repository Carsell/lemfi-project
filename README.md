# LemFi Fintech Analytics Project

A professional end-to-end data analytics pipeline simulating fintech transactional and user data. This project showcases data simulation, transformation, modeling, testing, and documentation using modern tools like dbt, PostgreSQL, and Tableau.

---

## Project Structure

fintech-analytics-project/
├── data/ # Raw simulated CSV files
├── dbt/lemfi_analytics/ # dbt project with models and seeds
│ ├── models/
│ ├── seeds/
│ ├── dbt_project.yml
│ └── schema.yml
├── dashboards/ # Tableau workbook and assets
├── notebooks/ # Data simulation Jupyter notebook
├── README.md
└── requirements.txt # Python dependencies

---

## Tools & Technologies Used

- Python (pandas, faker)
- PostgreSQL
- dbt (data build tool)
- Tableau (for data visualization)
- Git & GitHub (version control)

---

## Getting Started

### Setup Python Environment

pip install -r requirements.txt
Load Data and Build Models
bash
Copy
dbt seed
dbt run
dbt test
Generate Documentation
bash
Copy
dbt docs generate
dbt docs serve
Open your browser at http://localhost:8080 to explore your project documentation and lineage.

Key Features & KPIs
User verification growth over time

Transaction volume by country and currency

Flagged transaction trends for compliance

Risk scoring and KYC status tracking

### Author
Carsell Olukoya
GitHub | LinkedIn

### License
This project is licensed under the MIT License.

---

# How to add and push README.md to GitHub

1. Save your README.md file in your project root directory (`/Users/carsell/LemFi/`).

2. In your terminal, run:

git add README.md
git commit -m "Add polished README with project overview and instructions"
git push origin main
