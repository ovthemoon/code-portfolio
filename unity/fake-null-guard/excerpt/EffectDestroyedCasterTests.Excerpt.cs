// 발췌: 시전자가 파괴된 뒤의 효과 처리 테스트 일부. 원본은 Unity EditMode 테스트(UnityTest, 실제 GameObject)라 빌드에서 제외한다.
// using, 일부 테스트(중첩한 다른 시전자가 이어받는 경우 등)는 생략하고 주석을 정리했다.

/// <summary>
/// 효과를 건 영웅(시전자)이 파괴된 뒤의 처리. 2026-10-01 Character Lab 실측에서 영웅을 바꾸자 적마다
/// <c>EffectManager.Update</c> 가 매 프레임 MissingReferenceException(14초에 1,428건).
///
/// <para>원인: 시전자는 <see cref="IEffectTarget"/>(인터페이스)로 들고 있어 파괴돼도 C# 참조가 남는다.
/// <c>Caster?.GetTransform()</c> 의 <c>?.</c> 는 그걸 걸러내지 못하고 파괴된 transform 을 읽어 예외가 났다.
/// 예외가 루프 중간에 터져 그 적의 나머지 효과(만료 제거 포함)도 그 프레임에 처리되지 않았다.</para>
///
/// <para>정책: 시전자가 사라진 주기 효과(지속 피해, 지속 회복)는 계산할 시전자가 없으므로 즉시 끝낸다.
/// 틱이 없는 효과(디버프, 버프)는 시전자를 다시 읽지 않으므로 남은 시간 동안 그대로 유지된다.</para>
/// </summary>
public sealed class EffectDestroyedCasterTests
{
    private MockEffectTarget _owner;
    private EffectManager _manager;
    private DestroyableEffectTarget _caster;
    private DestroyableEffectTarget _otherCaster;

    [SetUp]
    public void SetUp()
    {
        _owner = new MockEffectTarget { Team = TeamID.Enemy };
        _manager = new EffectManager(_owner);
        _caster = new GameObject("__caster").AddComponent<DestroyableEffectTarget>();
        Assert.IsNotNull(_caster, "Support 어셈블리 MonoBehaviour 가 붙지 않았다");
        _otherCaster = new GameObject("__other_caster").AddComponent<DestroyableEffectTarget>();
    }

    [TearDown]
    public void TearDown()
    {
        if (_caster != null) Object.DestroyImmediate(_caster.gameObject);
        if (_otherCaster != null) Object.DestroyImmediate(_otherCaster.gameObject);
    }

    private SkillContext Context(ISkillEffect effect) => new SkillContext(_caster, _owner, null, effect);

    [Test]
    public void 파괴된_시전자만_파괴로_본다()
    {
        Assert.IsFalse(EffectTargetLifetime.IsDestroyed(null), "시전자 없음(null)은 파괴가 아니다");
        Assert.IsFalse(EffectTargetLifetime.IsDestroyed(_owner), "일반 C# 대상");
        Assert.IsFalse(EffectTargetLifetime.IsDestroyed(_caster));

        Object.DestroyImmediate(_caster.gameObject);

        Assert.IsTrue(EffectTargetLifetime.IsDestroyed(_caster));
        Assert.IsNull(EffectTargetLifetime.TransformOrNull(_caster), "파괴된 대상의 transform 을 읽지 않고 null");
    }

    [UnityTest]
    public IEnumerator 시전자가_파괴되면_지속피해는_오류없이_끝난다()
    {
        var effect = new PoisonDotEffect(new PoisonEffectConfig { Duration = 10f, tickInterval = 0.5f });
        yield return _manager.ApplyEffect(effect, Context(effect)).ToCoroutine();
        Assert.IsTrue(_manager.HasEffect(effect.ID), "전제: 독이 걸렸다");

        Object.DestroyImmediate(_caster.gameObject);

        Assert.DoesNotThrow(() => _manager.Update(0.6f), "틱 시점에 파괴된 시전자의 transform 을 읽으면 안 된다");
        Assert.IsFalse(_manager.HasEffect(effect.ID), "계산할 시전자가 없는 지속 피해는 끝낸다");
    }

    [UnityTest]
    public IEnumerator 시전자가_파괴돼도_디버프는_남은_시간만큼_유지된다()
    {
        var effect = new StatModifierEffect("attack_debuff", "공격력 감소", StatModifierType.AttackPower,
            20f, 3f, isPercentage: true, BuffType.Debuff);
        var dot = new PoisonDotEffect(new PoisonEffectConfig { Duration = 10f, tickInterval = 0.5f });
        yield return _manager.ApplyEffect(dot, Context(dot)).ToCoroutine();
        yield return _manager.ApplyEffect(effect, Context(effect)).ToCoroutine();
        Assert.IsTrue(_manager.HasEffect(effect.ID));

        Object.DestroyImmediate(_caster.gameObject);

        Assert.DoesNotThrow(() => _manager.Update(1f));
        Assert.IsFalse(_manager.HasEffect(dot.ID), "주기 효과를 정리한 뒤에도 다른 효과를 계속 처리한다");
        Assert.IsTrue(_manager.HasEffect(effect.ID), "틱이 없는 디버프는 시전자와 무관하게 유지");

        Assert.DoesNotThrow(() => _manager.Update(2.5f));
        Assert.IsFalse(_manager.HasEffect(effect.ID), "만료되면 정상 제거");
    }

    [UnityTest]
    public IEnumerator 시전자_없는_주기_효과는_파괴로_오인하지_않는다()
    {
        var effect = new PoisonDotEffect(new PoisonEffectConfig { Duration = 10f, tickInterval = 0.5f });
        var context = new SkillContext(null, _owner, null, effect);
        yield return _manager.ApplyEffect(effect, context).ToCoroutine();

        Assert.DoesNotThrow(() => _manager.Update(0.6f));

        Assert.IsTrue(_manager.HasEffect(effect.ID), "null 시전자와 파괴된 Unity 시전자는 다르게 처리한다");
    }

    // ...
}
