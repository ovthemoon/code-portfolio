"""재시도 허가는 불변이고 호출자 컨텍스트에 묶인 호스트 권한이다. annotation 은 허가가 아니다."""

import asyncio
from types import SimpleNamespace

import pytest

import read_retry_policy
from call_assessment import GATE_NONE, TrustPolicy, has_write_verb
from read_retry_policy import read_retry_scope, retry_read_allowed

READ = {"readOnlyHint": True}


@pytest.mark.parametrize("origins", [(None,), ("",)])
def test_invalid_origin_identity_cannot_authorize_retry(origins):
    with read_retry_scope(TrustPolicy(trusted_origins=origins)):
        assert not retry_read_allowed("svc__search", {}, READ)


def test_assessment_failure_cannot_authorize_retry(monkeypatch):
    def fail_assessment(*args, **kwargs):
        raise RuntimeError("assessment unavailable")

    monkeypatch.setattr(read_retry_policy, "assess_call", fail_assessment)
    with read_retry_scope(TrustPolicy(trusted_origins=("svc",))):
        assert not retry_read_allowed("svc__search", {}, READ)


@pytest.mark.parametrize("policy", [
    None,
    {},
    SimpleNamespace(trusted_origins=("svc",)),
    TrustPolicy(trusted_origins="svc"),
])
def test_missing_or_malformed_scope_cannot_authorize_retry(policy):
    with read_retry_scope(policy):
        assert not retry_read_allowed("svc__search", {}, READ)
    assert not retry_read_allowed("svc__search", {}, READ)


@pytest.mark.parametrize("field", ["trusted_origins", "read_verified_origins"])
def test_host_trusted_read_is_allowed(field):
    with read_retry_scope(TrustPolicy(**{field: ("svc",)})):
        assert retry_read_allowed("svc__search", {}, READ)
        assert not retry_read_allowed("other__search", {}, READ)


def test_untrusted_origin_claiming_read_only_is_not_allowed():
    with read_retry_scope(TrustPolicy()):
        assert not retry_read_allowed("svc__search", {}, READ)


@pytest.mark.parametrize("name,args,annotations", [
    ("svc__search", {}, {"readOnlyHint": 1}),
    ("svc__search", {}, {"readOnlyHint": True, "destructiveHint": True}),
    ("svc__delete_record", {}, READ),
    ("svc__search", {"path": "/home/user/.ssh/id_rsa"}, READ),
    ("svc__search", {}, None),
    ("search", {}, READ),
])
def test_permissive_policy_and_overrides_do_not_authorize_unsafe_retry(name, args, annotations):
    permissive = TrustPolicy(
        trusted_origins=("svc",), enabled=False, verb_check=False, sensitive_path_check=False,
        tool_overrides={name: {"gate": GATE_NONE, "risk": "read"}},
    )
    with read_retry_scope(permissive):
        assert not retry_read_allowed(name, args, annotations)


@pytest.mark.parametrize("name,args", [
    ("srv__sendEmail", {}),
    ("srv__deleteFile", {}),
    ("srv__createIssue", {}),
    ("srv__search", {"opts": {"path": "~/.ssh/id_rsa"}}),
    ("srv__search", {"files": [{"path": "~/.env"}], "note": "x"}),
])
def test_camel_case_write_verbs_and_nested_sensitive_paths_are_not_retried(name, args):
    with read_retry_scope(TrustPolicy(trusted_origins=("srv",))):
        assert not retry_read_allowed(name, args, READ)


@pytest.mark.parametrize("name,args", [
    ("srv__searchRecords", {"opts": {"query": "invoices", "tags": ["a", "b"]}}),
    ("srv__getUserProfile", {"filters": [{"id": "42"}]}),
])
def test_camel_case_read_names_and_clean_nested_args_are_still_retried(name, args):
    with read_retry_scope(TrustPolicy(trusted_origins=("srv",))):
        assert retry_read_allowed(name, args, READ)


@pytest.mark.parametrize("name", [
    "srv__sendEmail", "srv__deleteFile", "srv__XMLSend", "srv__v2Delete", "srv__list_and_sendAll",
])
def test_write_verbs_are_found_across_camel_case_boundaries(name):
    assert has_write_verb(name)


def test_fullwidth_write_verb_is_still_a_write_verb():
    assert has_write_verb("svc__ｄｅｌｅｔｅ_record")
    assert has_write_verb("svc__de\u200blete_record")
    assert not has_write_verb("svc__search_records")


def test_scope_snapshots_mutable_trust_and_restores_nested_scope_after_exception():
    trusted = ["svc"]
    policy = TrustPolicy(trusted_origins=trusted)
    with read_retry_scope(policy):
        trusted.clear()  # 스냅샷 뒤에 원본을 바꿔도 이 실행의 권한은 그대로다
        assert retry_read_allowed("svc__search", {}, READ)
        with pytest.raises(RuntimeError):
            with read_retry_scope(None):
                assert not retry_read_allowed("svc__search", {}, READ)
                raise RuntimeError("test exception")
        assert retry_read_allowed("svc__search", {}, READ)
    assert not retry_read_allowed("svc__search", {}, READ)


def test_parallel_tasks_keep_separate_retry_authority():
    async def scenario():
        entered = asyncio.Event()
        observed = asyncio.Event()

        async def trusted():
            with read_retry_scope(TrustPolicy(trusted_origins=("svc",))):
                entered.set()
                await observed.wait()
                assert retry_read_allowed("svc__search", {}, READ)

        async def untrusted():
            await entered.wait()
            assert not retry_read_allowed("svc__search", {}, READ)
            with read_retry_scope(TrustPolicy(trusted_origins=("other",))):
                assert not retry_read_allowed("svc__search", {}, READ)
                assert retry_read_allowed("other__search", {}, READ)
            observed.set()

        await asyncio.gather(trusted(), untrusted())
        assert not retry_read_allowed("svc__search", {}, READ)

    asyncio.run(scenario())
