import pandas as pd

# --- Global Cache ---
# Stores the results of slow web scraping tasks to serve instantly
cache_data = {
    "money_flow": [],
    "theme_list": pd.DataFrame(),
    "prophet_models": {}, # {ticker: forecast_data_list}
    "llm_sentiment": {}   # {ticker: {"data": dict, "updated_at": datetime}}
}
