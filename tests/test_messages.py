# -*- coding: utf-8 -*-
"""Role-grammar validation for the canonical transcript."""

import pytest

from celebrity.core import messages as m
from celebrity.providers.base import ToolCall


def test_valid_tool_sequence_passes():
    seq = [
        m.user('do it'),
        m.assistant_tool_calls([ToolCall(id='c1', name='list_tools', arguments={})]),
        m.tool_result('c1', '{}'),
    ]
    assert m.validate_sequence(seq) is True


def test_unpaired_tool_result_rejected():
    seq = [m.user('x'), m.tool_result('missing', '{}')]
    with pytest.raises(ValueError):
        m.validate_sequence(seq)


def test_duplicate_user_rejected():
    seq = [m.user('a'), m.user('b')]
    with pytest.raises(ValueError):
        m.validate_sequence(seq)
