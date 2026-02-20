"""Tests for gcgaap.config."""

import logging

import pytest

from gcgaap.config import GCGAAPConfig, default_config, setup_logging


class TestGCGAAPConfig:
    def test_default_values(self):
        cfg = GCGAAPConfig()
        assert cfg.numeric_tolerance == 0.01
        assert cfg.default_currency == "USD"

    def test_custom_tolerance(self):
        cfg = GCGAAPConfig(numeric_tolerance=0.001)
        assert cfg.numeric_tolerance == 0.001

    def test_custom_currency(self):
        cfg = GCGAAPConfig(default_currency="EUR")
        assert cfg.default_currency == "EUR"

    def test_is_zero_at_zero(self):
        cfg = GCGAAPConfig(numeric_tolerance=0.01)
        assert cfg.is_zero(0.0) is True

    def test_is_zero_within_tolerance(self):
        cfg = GCGAAPConfig(numeric_tolerance=0.01)
        assert cfg.is_zero(0.005) is True
        assert cfg.is_zero(-0.005) is True

    def test_is_zero_at_boundary(self):
        cfg = GCGAAPConfig(numeric_tolerance=0.01)
        assert cfg.is_zero(0.01) is True   # exactly at boundary

    def test_is_zero_outside_tolerance(self):
        cfg = GCGAAPConfig(numeric_tolerance=0.01)
        assert cfg.is_zero(0.011) is False
        assert cfg.is_zero(-0.011) is False

    def test_is_balanced_aliases_is_zero(self):
        cfg = GCGAAPConfig(numeric_tolerance=0.01)
        assert cfg.is_balanced(0.0) is True
        assert cfg.is_balanced(0.02) is False

    def test_default_config_singleton(self):
        assert default_config.numeric_tolerance == 0.01
        assert default_config.default_currency == "USD"


class TestSetupLogging:
    """
    logging.basicConfig is a no-op if the root logger already has handlers
    (as is typically the case in a pytest environment).  Test the call
    signature via mock rather than relying on the root logger level.
    """

    def test_info_level_passed_to_basic_config(self):
        from unittest.mock import patch as _patch

        with _patch("logging.basicConfig") as mock_cfg:
            setup_logging(verbose=False)

        mock_cfg.assert_called_once()
        assert mock_cfg.call_args.kwargs["level"] == logging.INFO

    def test_debug_level_passed_to_basic_config(self):
        from unittest.mock import patch as _patch

        with _patch("logging.basicConfig") as mock_cfg:
            setup_logging(verbose=True)

        mock_cfg.assert_called_once()
        assert mock_cfg.call_args.kwargs["level"] == logging.DEBUG
