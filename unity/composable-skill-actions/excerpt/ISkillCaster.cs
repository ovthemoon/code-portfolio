// 발췌: 스킬 실행이 시전자(뷰)에 기대는 지점을 가두는 포트 전체. 원본은 Unity 와 게임 서비스 타입에 의존해 빌드에서 제외한다.
// namespace 와 using 을 걷어 내고 주석을 정리했다. EffectPool, EntityMovement 등 반환 타입은 발췌에 없다.

/// <summary>
/// 스킬 액션과 컨텍스트가 구현 클래스 <see cref="EntityControllerBase"/>(MonoBehaviour 뷰) 대신
/// 이 포트에만 의존하게 해 스킬과 전투 도메인을 뷰에서 분리한다(포트 &amp; 어댑터).
///
/// 멤버는 <see cref="EntityControllerBase"/>의 기존 공개 프로퍼티와 시그니처를 그대로 따른다
/// (동작 불변, 어댑터는 위임만 한다). EffectPool, Movement, CutsceneManager, SkillController는 지금은
/// 엔티티별 구현 컴포넌트와 매니저를 그대로 노출한다. 이들의 인터페이스 추출과 UltimateCutsceneManager의
/// 역참조(FocusedCaster) 분리는 후속 단계로 미룬다(1차 목표는 스킬과 뷰 사이 결합 끊기).
/// </summary>
public interface ISkillCaster
{
    Transform Transform { get; }
    Vector3 Position { get; }
    EffectPool EffectPool { get; }
    EntityMovement Movement { get; }
    ISoundService SoundService { get; }
    UltimateCutsceneManager CutsceneManager { get; }
    IToastManager ToastManager { get; }
    SkillController SkillController { get; }
    CancellationToken DestroyToken { get; }

    void SetAnimationTimeScale(float timeScale);
    void PlayAnimation(string animationName, bool loop = false);
}
