from tools.state_race_checks import assert_double_sale_integrity, assert_publish_sale_integrity


def test_publication_cannot_resurrect_a_concurrently_sold_item(seller, item_input):
    assert_publish_sale_integrity(seller['client'], seller['csrf'], item_input)


def test_concurrent_sales_return_one_success_and_one_conflict(seller, item_input):
    assert_double_sale_integrity(seller['client'], seller['csrf'], item_input)
