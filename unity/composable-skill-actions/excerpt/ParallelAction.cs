// 발췌: 자식 액션을 동시에 실행하는 조합 액션. 원본은 UniTask 와 Unity 직렬화에 의존해 빌드에서 제외한다.
// 에디터 표시용 어트리뷰트(Odin 등)와 자식별 로깅 래퍼는 걷어 냈다. 로거는 Unity Debug 로 바꾸고 주석을 정리했다.

/// <summary>자식 Action 을 동시에 실행하고, 모두 끝나야 이 Action 도 끝난다.</summary>
[Serializable]
public class ParallelAction : ISkillAction
{
    public string ActionName => "병렬 실행";

    public string GetSummary()
    {
        if (ActionsToRunInParallel == null || ActionsToRunInParallel.Count == 0)
            return "병렬 실행 (액션 없음)";
        return $"병렬 실행 ({ActionsToRunInParallel.Count}개 액션)";
    }

    // 인터페이스 목록을 Inspector 에서 조합하려면 [SerializeReference] 가 핵심이다.
    [SerializeReference]
    public List<ISkillAction> ActionsToRunInParallel = new List<ISkillAction>();

    /// <summary>한 액션이 실패하면 나머지 액션을 취소할지 여부</summary>
    public bool CancelAllOnFailure = false;

    public async UniTask ExecuteAsync(SkillExecutionContext context, CancellationToken ct)
    {
        if (ActionsToRunInParallel == null || ActionsToRunInParallel.Count == 0)
        {
            Debug.LogWarning("[ParallelAction] 실행할 액션이 없습니다.");
            return;
        }

        CancellationTokenSource linkedCts = null;
        CancellationToken effectiveCt = ct;

        if (CancelAllOnFailure)
        {
            linkedCts = CancellationTokenSource.CreateLinkedTokenSource(ct);
            effectiveCt = linkedCts.Token;
        }

        try
        {
            var tasks = new List<UniTask>();

            for (int i = 0; i < ActionsToRunInParallel.Count; i++)
            {
                var action = ActionsToRunInParallel[i];
                if (action != null)
                {
                    tasks.Add(action.ExecuteAsync(context, effectiveCt));
                }
            }

            await UniTask.WhenAll(tasks);
        }
        catch (OperationCanceledException)
        {
            Debug.LogWarning("[ParallelAction] 병렬 실행이 취소되었습니다.");
            throw;
        }
        catch (Exception ex)
        {
            Debug.LogError($"[ParallelAction] 병렬 실행 중 예외 발생: {ex.Message}");

            if (CancelAllOnFailure && linkedCts != null)
            {
                linkedCts.Cancel();
                Debug.LogWarning("[ParallelAction] 실패로 인해 모든 액션 취소");
            }

            throw;
        }
        finally
        {
            linkedCts?.Dispose();
        }
    }
}
