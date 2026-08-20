import logging

import pandas as pd

import main as batch_application


def test_csv_pipeline_generates_report_and_quarantine_outputs(
    csv_pipeline_environment,
):
    """
    tests the complete CSV validation quarantine and reconciliation workflow
    :param csv_pipeline_environment: isolated pipeline paths and sample CSV data
    :returns: none
    """
    output_dir = csv_pipeline_environment["output_dir"]

    batch_application.main()

    report = pd.read_csv(output_dir / "reconciliation_report.csv")
    invalid_customers = pd.read_csv(output_dir / "invalid_customers.csv")
    invalid_orders = pd.read_csv(output_dir / "invalid_orders.csv")
    invalid_payments = pd.read_csv(output_dir / "invalid_payments.csv")

    assert report["order_id"].tolist() == [5001]
    assert report.iloc[0]["financial_status"] == "paid"
    assert report.iloc[0]["email"] == "john@example.com"
    assert invalid_customers.iloc[0]["validation_errors"] == "invalid email"
    assert invalid_orders.iloc[0]["validation_errors"] == "customer failed validation"
    assert invalid_payments.iloc[0]["validation_errors"] == "order failed validation"


def test_csv_pipeline_logs_fatal_structural_validation_error(
    csv_pipeline_environment,
    caplog,
):
    """
    tests that structural validation failure is logged without writing reports
    :param csv_pipeline_environment: isolated pipeline paths and sample CSV data
    :param caplog: pytest fixture for capturing log messages
    :returns: none
    """
    data_dir = csv_pipeline_environment["data_dir"]
    output_dir = csv_pipeline_environment["output_dir"]
    customers = pd.DataFrame(
        [{"customer_id": 1001, "name": "John Smith", "email": "john@example.com"}]
    )
    customers.to_csv(data_dir / "customers.csv", index=False)

    with caplog.at_level(logging.ERROR):
        batch_application.main()

    assert "customers is missing required columns" in caplog.text
    assert not (output_dir / "reconciliation_report.csv").exists()
