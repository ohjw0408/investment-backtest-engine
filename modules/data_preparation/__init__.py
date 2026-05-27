"""
modules/data_preparation
공통 시나리오 데이터 준비 facade.

주요 API:
    from modules.data_preparation import prepare_scenario_data
"""
from .scenario_data_preparer import prepare_scenario_data

__all__ = ["prepare_scenario_data"]
