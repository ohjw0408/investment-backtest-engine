import logging
import warnings
import subprocess
import os

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")
os.environ["PYTHONWARNINGS"] = "ignore"


tests = [
    "test_basic_simulation.py",
    "test_engine_stress.py",
    "test_multi_asset.py",
    "test_rebalance.py",
    "test_portfolio_accounting.py",
    "test_weight_drift.py",
    "test_dividend_flow.py",
    "test_rebalance_turnover.py",
    "test_missing_price.py",
    "test_engine_integrity.py",
    "test_dca_engine.py",
    "test_cash_and_dividend_engine.py"
]

print("\n====================================")
print("Running All Tests")
print("====================================\n")

for test in tests:

    print(f"\n----- {test} -----\n")

    subprocess.run(
        ["py", os.path.join("tests", test)],
        check=False
    )

print("\n====================================")
print("All Tests Finished")
print("====================================")