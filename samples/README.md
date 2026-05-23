# ExecSlate — Sample CSVs for the Analytics Tab

Drop any of these into the Analytics tab to test the workspace. Each
file exercises a different path of the chart-intelligence engine.

| File | Tests | Expected primary chart |
|------|-------|------------------------|
| `monthly_revenue.csv` | Time-series detection (the `month` column) | **Trend** over time |
| `customer_segments.csv` | Categorical / segment data, no time column | **Ranking** bar chart |
| `q1_sales.csv` + `q2_sales.csv` + `q3_sales.csv` | Multi-file ordered upload — must be added in that order | **Trend** (combined timeline) |

## How to use

### 1. Single-file test (time-series)
- Open Analytics tab on any project.
- Upload `monthly_revenue.csv` alone.
- You should see a trend chart with months on the x-axis, plus a regional breakdown as the secondary view.

### 2. Single-file test (categorical / ranking)
- Upload `customer_segments.csv` alone.
- The primary chart should be a **ranking bar** of segments by `customer_count` — *not* a fake trend line.
- The "Pattern" chip should read **Categorical** (not "Increasing/Decreasing").
- Growth chip should be hidden (no time dimension).

### 3. Multi-file ordered upload
- Upload `q1_sales.csv`, `q2_sales.csv`, `q3_sales.csv` together.
- Use the ▲ ▼ arrows to order them: **Q1 → Q2 → Q3**.
- Click **Analyse Data →**. The engine stacks them in sequence and treats it as one 9-month dataset.

### 4. Error-recovery test
- Try uploading `monthly_revenue.csv` together with `customer_segments.csv` (different columns).
- You should see an **inline red banner** explaining the column mismatch — *not* a full-page 400.
- The upload form stays visible so you can fix and retry.

### 5. Editable insights + Send to Report
- After any successful upload, click on one of the AI observations on the right.
- Edit the text → press Enter (or click away). A green "✓ saved" mark should flash briefly.
- Pin a couple of observations, add a note, then click **Send to Report →**.
- You'll land on the Report tab with the observations + your notes pre-populated in the working theory.

## Note on data realism
These are fictional but consulting-shaped numbers (a hypothetical SaaS
company with Enterprise / Mid-Market / SMB segments). They're meant to
demonstrate the workflow, not to be benchmarks.
