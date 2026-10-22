"""All inference in this file is MOCKED; it does not validate a live model."""

import json
from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest
from conftest import plan
from pydantic import ValidationError

from campuspulse.gemma_client import GemmaClient
from campuspulse.models import AIError, AnalysisPlan, Filter
from campuspulse.question_planner import (
    parse_plan,
    plan_question,
    schema_context,
    suggested_questions,
)


def mocked_client(settings, response=None):
    transport = Mock()
    transport.list.return_value = {"models": [{"model": settings.ollama_model}]}
    transport.chat.return_value = {"message": {"content": response or plan().model_dump_json()}}
    return GemmaClient(settings, client=transport), transport


def test_parse_valid_json(dataset):
    assert parse_plan(plan().model_dump_json(), dataset).intent == "aggregate"


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "```json\n{}\n```",
        "{}",
        '{"intent":"eval"}',
        '{"intent":"aggregate","metric":"electricity_kwh","aggregation":"sum","code":"import os"}',
    ],
)
def test_parse_invalid_json(text, dataset):
    with pytest.raises(AIError):
        parse_plan(text, dataset)


@pytest.mark.parametrize(
    "update",
    [
        {"metric": "__import__"},
        {"aggregation": "exec"},
        {"group_by": ["source_file"]},
        {"filters": [{"column": "month", "operator": "eq", "value": "June"}]},
        {"filters": [{"column": "building_name", "operator": "gte", "value": "A"}]},
        {"filters": [{"column": "electricity_kwh", "operator": "eq", "value": "5"}]},
    ],
)
def test_reject_unsafe_or_invalid_plans(dataset, update):
    with pytest.raises(AIError):
        parse_plan(json.dumps(plan().model_dump() | update), dataset)


def test_required_fields_and_filter_types():
    with pytest.raises(ValidationError):
        AnalysisPlan(intent="aggregate", metric="electricity_kwh")
    with pytest.raises(ValidationError):
        Filter(column="month", operator="in", value="2026-06")
    with pytest.raises(ValidationError):
        Filter(column="electricity_kwh", operator="eq", value=float("inf"))


@pytest.mark.parametrize(
    "question",
    [
        "What is the total electricity usage?",
        "Sabse zyada electricity kis building ne use ki?",
        "सबसे अधिक बिजली किस इमारत ने उपयोग की?",
    ],
)
def test_mocked_multilingual_request(settings, dataset, question):
    client, transport = mocked_client(settings)
    result = plan_question(question, dataset, settings, client)
    assert result.intent == "aggregate"
    call = transport.chat.call_args.kwargs
    assert call["model"] == settings.ollama_model
    assert call["format"] == AnalysisPlan.model_json_schema()
    payload = json.loads(call["messages"][1]["content"])
    assert payload["question"] == question
    assert "electricity_kwh" not in payload["dataset"]  # Schema, not numeric row arrays.
    assert "source_file" not in json.dumps(payload)
    assert "6200" not in json.dumps(payload)


def test_remote_requires_disclosure(settings, dataset):
    remote = replace(settings, ollama_host="https://private-inference.example.org")
    client, transport = mocked_client(remote)
    with pytest.raises(AIError, match="remote processing"):
        plan_question("total?", dataset, remote, client)
    transport.chat.assert_not_called()
    assert plan_question("total?", dataset, remote, client, allow_remote=True)


@pytest.mark.parametrize(
    "error",
    [ConnectionError(), httpx.ConnectError("test failure"), httpx.ReadTimeout("test timeout")],
)
def test_connection_and_timeout_handling(settings, error):
    client, transport = mocked_client(settings)
    transport.list.side_effect = error
    assert not client.check().ready
    with pytest.raises(AIError):
        client.plan_json("system", "question")


def test_mocked_inference_timeout(settings, dataset):
    client, transport = mocked_client(settings)
    transport.chat.side_effect = httpx.ReadTimeout("test timeout")
    with pytest.raises(AIError, match="timed out"):
        plan_question("total?", dataset, settings, client)


def test_missing_model_no_substitution(settings):
    client, transport = mocked_client(settings)
    transport.list.return_value = {"models": [{"model": "gemma3:4b"}]}
    assert not client.check().ready
    with pytest.raises(AIError):
        client.plan_json("system", "question")
    transport.chat.assert_not_called()


def test_invalid_model_list_does_not_crash(settings):
    client, transport = mocked_client(settings)
    transport.list.return_value = {"models": [None]}
    status = client.check()
    assert not status.ready
    assert "invalid model list" in status.message


def test_mocked_malformed_output(settings, dataset):
    client, _ = mocked_client(settings, "This is not a plan")
    with pytest.raises(AIError, match="invalid"):
        plan_question("total?", dataset, settings, client)


def test_unsupported_and_cost_guards(settings, dataset):
    client, _ = mocked_client(settings)
    assert (
        plan_question("Who wastes electricity?", dataset, settings, client).intent == "unsupported"
    )
    assert (
        plan_question("Electricity cost in December?", dataset, settings, client).metric
        == "electricity_cost_inr"
    )


def test_context_and_suggestions(settings, dataset):
    context = schema_context(dataset, settings)
    assert context["calendar_timezone"] == "Asia/Kolkata"
    assert context["available_months"][-1] == "2026-06"
    assert "2026-05 and 2026-06" in suggested_questions(dataset)[1]
