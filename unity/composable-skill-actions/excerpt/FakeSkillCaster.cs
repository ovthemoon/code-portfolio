// 발췌: ISkillCaster 의 테스트 대역 전체. 원본은 Unity 테스트 어셈블리에서 임시 GameObject 를 쓰므로 빌드에서 제외한다.
// namespace 와 using 을 걷어 내고 주석을 정리했다.

/// <summary>
/// ISkillCaster 포트의 테스트 대역. 스킬 도메인을 씬, 백엔드, DI 없이 실행하고 관측한다.
///
/// EffectPool, Movement, CutsceneManager, SkillController 는 아직 인터페이스를 뽑지 않아 null 을 돌려준다.
/// 이들을 요구하는 액션은 검증 대상 밖이고 순수 포트 액션만 검증할 수 있다(점진 1차).
/// Transform 은 Unity sealed 타입이라 가짜 객체로 대체할 수 없어 임시 GameObject 로 제공하고 Dispose 로 정리한다.
/// </summary>
public sealed class FakeSkillCaster : ISkillCaster, IDisposable
{
    private readonly GameObject _go;

    public FakeSkillCaster()
    {
        _go = new GameObject("FakeSkillCaster");
    }

    public Transform Transform => _go.transform;
    public Vector3 Position => _go.transform.position;
    public void SetPosition(Vector3 p) => _go.transform.position = p;

    // 구현 컴포넌트라 가짜 객체로 대체할 수 없다. 이를 쓰는 액션은 검증 대상 밖이다
    public EffectPool EffectPool => null;
    public EntityMovement Movement => null;
    public UltimateCutsceneManager CutsceneManager => null;
    public SkillController SkillController => null;

    // 서비스 포트. 필요하면 레코더나 스텁을 주입한다
    public ISoundService SoundService { get; set; }
    public IToastManager ToastManager { get; set; }
    public CancellationToken DestroyToken { get; set; } = CancellationToken.None;

    public readonly List<float> AnimTimeScales = new();
    public void SetAnimationTimeScale(float timeScale) => AnimTimeScales.Add(timeScale);

    public readonly List<string> AnimationsPlayed = new();
    public void PlayAnimation(string animationName, bool loop = false) => AnimationsPlayed.Add(animationName);

    public void Dispose()
    {
        if (_go != null) UnityEngine.Object.DestroyImmediate(_go);
    }
}
