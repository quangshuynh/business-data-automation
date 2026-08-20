import pandas as pd
import pytest

import main as batch_application


@pytest.fixture
def csv_pipeline_environment(tmp_path, monkeypatch):
    """
    creates isolated CSV input and output directories for pipeline tests
    :param tmp_path: pytest fixture providing a temporary directory
    :param monkeypatch: pytest fixture for changing application configuration
    :returns: dictionary containing pipeline input and output paths
    """
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    data_dir.mkdir()

    customers = pd.DataFrame(
        [
            {
                "customer_id": 1001,
                "name": "John Smith",
                "email": "JOHN@EXAMPLE.COM",
                "phone": "5855551234",
            },
            {
                "customer_id": 1002,
                "name": "Jane Doe",
                "email": "bad-email",
                "phone": "5855552222",
            },
        ]
    )
    orders = pd.DataFrame(
        [
            {
                "order_id": 5001,
                "customer_id": 1001,
                "date": "2026-08-01",
                "total": 100.00,
            },
            {
                "order_id": 5002,
                "customer_id": 1002,
                "date": "2026-08-02",
                "total": 75.00,
            },
        ]
    )
    payments = pd.DataFrame(
        [
            {
                "payment_id": 9001,
                "order_id": 5001,
                "amount": 100.00,
                "transaction_type": "payment",
                "status": "paid",
            },
            {
                "payment_id": 9002,
                "order_id": 5002,
                "amount": 75.00,
                "transaction_type": "payment",
                "status": "paid",
            },
        ]
    )

    customers.to_csv(data_dir / "customers.csv", index=False)
    orders.to_csv(data_dir / "orders.csv", index=False)
    payments.to_csv(data_dir / "payments.csv", index=False)

    monkeypatch.setattr(batch_application, "DATA_DIR", data_dir)
    monkeypatch.setattr(batch_application, "OUTPUT_DIR", output_dir)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    return {"data_dir": data_dir, "output_dir": output_dir}
