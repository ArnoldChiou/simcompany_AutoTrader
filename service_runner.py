"""Stable entry point for detached SimCompanies background services."""

import argparse

from main import (
    run_auto_buyer,
    run_building_construction_monitor,
    run_power_plant_producer,
)
from production_monitor import setup_logger


def run_service(service):
    if service == "autobuyer":
        run_auto_buyer()
        return
    if service == "powerplant":
        logger = setup_logger("production_monitor.powerplant", "monitor_powerplant.log")
        run_power_plant_producer(logger)
        return
    if service == "construction":
        logger = setup_logger("production_monitor.activity", "monitor_activity.log")
        run_building_construction_monitor(logger)
        return
    raise ValueError(f"Unknown service: {service}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("service", choices=("autobuyer", "powerplant", "construction"))
    args = parser.parse_args()
    run_service(args.service)


if __name__ == "__main__":
    main()
