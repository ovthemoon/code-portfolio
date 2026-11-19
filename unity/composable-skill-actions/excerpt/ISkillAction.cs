// 발췌: 스킬 동작의 기본 인터페이스 전체. 원본은 UniTask 와 Unity 컨텍스트 타입에 의존해 빌드에서 제외한다.
// namespace 와 using 을 걷어 내고 주석을 정리했다. SkillExecutionContext 는 발췌에 없다.

/// <summary>SkillExecutionContext 를 받아 실행되는 "레고 블록" 단위</summary>
public interface ISkillAction
{
    /// <summary>UI 표시용 이름</summary>
    string ActionName { get; }

    /// <summary>
    /// Inspector 에서 보여줄 짧은 설명.
    /// 예: "Attack 애니메이션 재생", "0.5초 대기", "범위 내 적에게 데미지"
    /// </summary>
    string GetSummary() => ActionName;

    /// <param name="context">Caster, Target, Skill 등을 담는다</param>
    UniTask ExecuteAsync(SkillExecutionContext context, CancellationToken ct);
}
