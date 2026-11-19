// 발췌: 에이전트 이모트 컨트롤러에서 질문 대기(물음표) 상태를 정하는 부분.
// 원본은 Unity 컴포넌트와 승인 큐 서비스에 의존해 빌드에서 제외한다. 생략한 부분은 ... 로 표시하고 주석을 정리했다.

public sealed class AgentEffectController : MonoBehaviour
{
    // ... (필드: _agents, _approvalQueue 등. 각 에이전트 항목에 PendingApproval, AskIds 가 있다)

    // 승인(질문) 신호는 승인 큐(인박스)를 거치며 인터랙션 모달과 별개로 합류한다.
    // change.Request 는 무시하고 매번 생성된 전원을 현재 큐로 다시 계산한다.
    // MiddlewareApprovalQueueService.RefreshAsync(재접속 뒤 다시 불러오기)는 대표 항목 1개(큐가
    // 비면 null)만 실어 OnChanged 를 한 번 내보내는 계약이라, 그 항목의 agentId 로만 다시 계산하면
    // 나머지 에이전트(특히 rep==null 인 빈 큐는 전원)는 재계산이 일어나지 않아 상태 어긋남이 남는다.
    // AgentCharacterController.PushAwaitingUser 와 같은 계약을 공유한다
    // (AgentEmoteLogic.HasAwaitingApproval).
    private void HandleApprovalChanged(ApprovalChange change)
    {
        if (_approvalQueue == null || _agents.Count == 0) return;
        var items = _approvalQueue.GetAll();
        var onlyAgent = _agents.Count == 1;
        foreach (var kv in _agents)
        {
            var e = kv.Value;
            e.PendingApproval = UsesWorkState
                ? AgentEmoteLogic.ShouldAwaitUserByContract(false, items, kv.Key, onlyAgent)
                : AgentEmoteLogic.HasAwaitingApproval(items, kv.Key, onlyAgent);
            Refresh(e);
        }
    }

    // 턴이 끝나면 그 턴의 질문 모달도 함께 끝난다(질문은 턴을 막으므로 턴보다 오래 살 수 없다).
    // 유저가 답해서 끝났든, 취소/오류/무응답 상한으로 끝났든 물음표는 내려가야 한다.
    private void HandleTurnEndedForAsk(ChatFinalEvent e) => ClearAsksFor(e.AgentId);
    private void HandleTurnErrorForAsk(ChatError e) => ClearAsksFor(e.AgentId);

    private void ClearAsksFor(string agentId)
    {
        var e = ResolveEntry(agentId);
        if (e == null || e.AskIds.Count == 0) return;
        e.AskIds.Clear();
        Refresh(e);
    }

    /// <summary>유저가 카드에 답을 보내면 그 tool_use_id 의 대기만 해제한다(다른 카드는 유지).
    /// 응답은 agent 라우팅 정보 없이 id 만 오므로 id 를 가진 엔트리에서 지운다(id 는 전역 유일).</summary>
    private void HandleToolUserResponseSent(string toolUseId)
    {
        if (string.IsNullOrEmpty(toolUseId)) return;
        foreach (var e in _agents.Values)
        {
            if (!e.AskIds.Remove(toolUseId)) continue;
            Refresh(e);
            return;
        }
    }

    // ...
}
