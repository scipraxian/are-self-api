from unittest.mock import MagicMock, patch

import pytest

from common.queries import guess_model


def make_mock_model(name, app_label):
    model = MagicMock()
    model.__name__ = name
    model._meta.app_label = app_label
    return model


def make_mock_app_config(models):
    app_config = MagicMock()
    app_config.get_models.return_value = models
    return app_config


@pytest.fixture
def mock_apps():
    user_model = make_mock_model('UserProfile', 'accounts')
    order_model = make_mock_model('Order', 'shop')
    order_item_model = make_mock_model('OrderItem', 'shop')

    configs = [
        make_mock_app_config([user_model]),
        make_mock_app_config([order_model, order_item_model]),
    ]

    with patch('django.apps.apps.get_app_configs', return_value=configs):
        yield


def test_exact_match(mock_apps):
    result = guess_model('UserProfile')
    assert result.success is True
    assert result.app_label == 'accounts'
    assert result.model_class.__name__ == 'UserProfile'
    assert 'accounts' in result.message


def test_case_insensitive_match(mock_apps):
    result = guess_model('userprofile')
    assert result.success is True
    assert result.model_class.__name__ == 'UserProfile'


def test_no_match(mock_apps):
    result = guess_model('Invoice')
    assert result.success is False
    assert result.model_class is None
    assert 'Invoice' in result.message


def test_close_match_suggestion(mock_apps):
    result = guess_model('Order')  # exact match
    assert result.success is True

    result = guess_model('order')  # also exact, case-insensitive
    assert result.success is True


def test_close_match_no_exact(mock_apps):
    # "Item" is not an exact match but is contained in "OrderItem"
    result = guess_model('Item')
    assert result.success is False
    assert 'OrderItem' in result.message
    assert 'Did you mean' in result.message
