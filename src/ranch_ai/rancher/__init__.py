"""Phone-app back end: observed-data status rules, nightly worker, light API.

Import submodules directly (``ranch_ai.rancher.store``, ``.api``) so the API
process never pulls in pandas, scikit-learn or rasterio.
"""
