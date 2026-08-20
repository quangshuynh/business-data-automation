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

    result = batch_application.main()

    report = pd.read_csv(output_dir / "reconciliation_report.csv")
    invalid_customers = pd.read_csv(output_dir / "invalid_customers.csv")
    invalid_orders = pd.read_csv(output_dir / "invalid_orders.csv")
    invalid_payments = pd.read_csv(output_dir / "invalid_payments.csv")

    assert result == 0
    assert report["order_id"].tolist() == [5001]
    assert report.iloc[0]["financial_status"] == "paid"
    assert report.iloc[0]["payment_count"] == 1
    assert report.iloc[0]["outstanding_balance"] == 0.00
    assert report.iloc[0]["overpayment_amount"] == 0.00
    assert report.iloc[0]["discrepancy_flags"] != "order has no payments"
    assert pd.notna(report.iloc[0]["reconciliation_timestamp"])
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
        result = batch_application.main()

    assert result == 1
    assert "customers is missing required columns" in caplog.text
    assert not (output_dir / "reconciliation_report.csv").exists()


def test_csv_pipeline_logs_missing_input_file(
    csv_pipeline_environment,
    caplog,
):
    """
    tests that a missing input file returns a failure status and logs the error
    :param csv_pipeline_environment: isolated pipeline paths and sample CSV data
    :param caplog: pytest fixture for capturing log messages
    :returns: none
    """
    data_dir = csv_pipeline_environment["data_dir"]
    (data_dir / "orders.csv").unlink()

    with caplog.at_level(logging.ERROR):
        result = batch_application.main()

    assert result == 1
    assert "file processing failed" in caplog.text


def test_csv_pipeline_persists_valid_records_when_configured(
    csv_pipeline_environment,
    monkeypatch,
):
    """
    tests that configured persistence receives each validated dataset
    :param csv_pipeline_environment: isolated pipeline paths and sample CSV data
    :param monkeypatch: pytest fixture for replacing persistence behavior
    :returns: none
    """
    received_counts = {}

    def fake_persist_valid_data(customers, orders, payments):
        """
        records validated dataset sizes passed by the pipeline
        :param customers: dataframe containing validated customers
        :param orders: dataframe containing validated orders
        :param payments: dataframe containing validated payments
        :returns: dictionary containing persisted record counts
        """
        received_counts.update(
            customers=len(customers),
            orders=len(orders),
            payments=len(payments),
        )
        return received_counts

    monkeypatch.setattr(batch_application, "is_database_configured", lambda: True)
    monkeypatch.setattr(
        batch_application,
        "persist_valid_data",
        fake_persist_valid_data,
    )

    result = batch_application.main()

    assert result == 0
    assert received_counts == {"customers": 1, "orders": 1, "payments": 1}


def test_database_failure_does_not_block_csv_outputs(
    csv_pipeline_environment,
    monkeypatch,
    caplog,
):
    """
    tests that a database failure is logged while CSV reporting completes
    :param csv_pipeline_environment: isolated pipeline paths and sample CSV data
    :param monkeypatch: pytest fixture for replacing persistence behavior
    :param caplog: pytest fixture for capturing log messages
    :returns: none
    """
    output_dir = csv_pipeline_environment["output_dir"]

    def fail_persistence(customers, orders, payments):
        """
        raises a database persistence error for pipeline testing
        :param customers: dataframe containing validated customers
        :param orders: dataframe containing validated orders
        :param payments: dataframe containing validated payments
        :returns: none
        """
        raise batch_application.DatabasePersistenceError("database unavailable")

    monkeypatch.setattr(batch_application, "is_database_configured", lambda: True)
    monkeypatch.setattr(batch_application, "persist_valid_data", fail_persistence)

    with caplog.at_level(logging.ERROR):
        result = batch_application.main()

    assert result == 0
    assert "database persistence failed" in caplog.text
    assert (output_dir / "reconciliation_report.csv").exists()
