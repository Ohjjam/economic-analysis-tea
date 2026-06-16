# Economic Analysis — Process TEA Tool

An interactive **Techno-Economic Analysis (TEA)** web app for electrochemistry / plastic /
biomass / hydrogen / CO₂RR processes. Build a process flow diagram, then get a
paper-quality CAPEX / OPEX / Revenue / MSP / sensitivity analysis, exportable to Excel.

## ▶️ Open the app (no install)

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=Ohjjam/economic-analysis-tea&branch=main&mainModule=tea_tool/app.py)

Click the badge above. The first time, log in with GitHub (free) and press **Deploy** —
after that it's a permanent link anyone can open and use in the browser. No Python, no setup.

> Already deployed? The live link will look like `https://<name>.streamlit.app` — paste it here once it exists.

## 🖥️ Run locally instead

```bash
cd tea_tool
pip install -r requirements.txt
streamlit run app.py
```

On Windows you can also double-click `tea_tool/run.bat`.

## 📂 What's inside

- `tea_tool/` — the app (`app.py`), TEA engine, process models, experiments, MATLAB sizing layer
- `Article/` — source papers and reference TEA spreadsheets
- See [`tea_tool/README.md`](tea_tool/README.md) for the full feature guide (Korean + English)
