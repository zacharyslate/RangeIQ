# Example Workflow

1. Start with the bundled `data/example/caja_caliente_ranch.geojson` for the Caja Caliente starter scenario.
2. Run `python -m ranch_ai` to build synthetic weekly data, multi-year history, and the RanchIQ monthly report.
3. Inspect the exported CSV and Markdown files in `data/processed/`.
4. Launch `streamlit run app/dashboard.py`.
5. Review the ranch map, pasture condition score, vegetation trend, rainfall deficit, drought status, water risk, and stocking recommendation.
6. Replace the bundled starter boundary with your updated ranch or pasture geometry whenever you want to refine the map.
7. Later, replace synthetic providers with real public-data providers while keeping the same weekly table contract.
