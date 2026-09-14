from procureai.synthetic.generator import generate_suppliers, inject_deterioration


def test_generator_is_reproducible_and_correlated():
    first = generate_suppliers(10, 42)
    assert first == generate_suppliers(10, 42)
    assert len({row["supplier_code"] for row in first}) == 10
    assert all(55 <= row["base_quality"] <= 99 for row in first)


def test_scenario_ground_truth():
    rows = generate_suppliers(20, 42)
    code = next(row["supplier_code"] for row in rows if row["country"] == "DE")
    assert inject_deterioration(rows, code)["injected"] is True
