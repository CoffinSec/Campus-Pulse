"""Regression tests for thought-part response parsing and common chat requests.

No external API is contacted.
"""
import json
from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest

from campuspulse.config import Settings
from campuspulse.gemma_client import GemmaClient
from campuspulse.models import AIError, AnalysisPlan
from campuspulse.question_planner import plan_question
from campuspulse.quick_replies import quick_reply


@pytest.mark.parametrize('q', ['hi', 'hello', 'hey', 'namaste'])
def test_greeting_replies_without_planner(dataset, q):
    text = quick_reply(q, dataset)
    assert text and 'Hi!' in text
    assert 'summary' in text


@pytest.mark.parametrize('q', ['give me a summary', 'please give me a summary', 'summarize my data', 'report ka summary'])
def test_verified_summary_uses_uploaded_data(dataset, q):
    text = quick_reply(q, dataset)
    assert '120,500 kWh' in text
    assert 'Boys Hostel (32,200 kWh)' in text
    assert '6 missing occupancy values' not in text
    assert 'SYNTHETIC' in text


def test_nonmatching_question_routes_to_ai(dataset):
    assert quick_reply('Which building was highest in May 2026?', dataset) is None


def test_response_skips_thinking_part_and_keeps_complete_json(monkeypatch):
    calls = []
    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, json=None, headers=None):
            calls.append((url, json, headers))
            return httpx.Response(200, json={
                'candidates': [{
                    'content': {'parts': [
                        {'thought': True, 'text': '{"intent":"unsupported"}'},
                        {'text': '```json\n'},
                        {'text': '{"intent":"aggregate","metric":"electricity_kwh","aggregation":"sum"}'},
                        {'text': '\n```'},
                    ]}
                }]
            })
    monkeypatch.setattr(httpx, 'Client', FakeHttpClient)
    settings = replace(Settings(), gemini_api_key='private-test-key')
    answer = GemmaClient(settings).plan_json('system', '{}')
    assert json.loads(answer)['intent'] == 'aggregate'
    assert 'key=' not in calls[0][0] and 'private-test-key' not in calls[0][0]
    assert calls[0][2]['x-goog-api-key'] == 'private-test-key'
    assert calls[0][1]['generationConfig']['thinkingConfig']['thinkingLevel'] == 'minimal'


def test_one_retry_on_malformed_plan(dataset):
    client = Mock()
    client.plan_json.side_effect = [
        '{"intent":"aggregate","metric":"electricity_kwh"}',
        AnalysisPlan(intent='aggregate', metric='electricity_kwh', aggregation='sum').model_dump_json(),
    ]
    settings = Settings()
    result = plan_question('Total usage?', dataset, settings, client)
    assert result.intent == 'aggregate'
    assert client.plan_json.call_count == 2
    assert 'failed strict plan validation' in client.plan_json.call_args.args[0]


def test_reject_still_invalid_plans(dataset):
    client = Mock()
    client.plan_json.return_value = '{"intent":"aggregate","metric":"__import__","aggregation":"sum"}'
    with pytest.raises(AIError, match='invalid or unsupported'):
        plan_question('Total usage?', dataset, Settings(), client)
    assert client.plan_json.call_count == 2
