// 발췌: EffectManager 에서 파괴된 시전자를 거르는 부분.
// 원본은 Unity 와 효과 시스템 전체에 의존해 빌드에서 제외한다. 생략한 부분은 ... 로 표시하고 주석을 정리했다.

public class EffectManager
{
    public async UniTask ApplyEffect(ISkillEffect effect, SkillContext context)
    {
        // 이미 사라진 시전자(투사체가 뒤늦게 맞은 경우 등)의 효과는 걸지 않는다. 적용과 틱이 시전자를 다시 읽기 때문이다.
        if (context != null && EffectTargetLifetime.IsDestroyed(context.Caster)) return;
        // ...
    }

    /// <summary>밀린 틱을 간격만큼 차감하며 처리한다. 주인이 죽었으면 false.</summary>
    private bool ProcessTicks(string key, ActiveEffect activeEffect, IPeriodicEffect periodicEffect)
    {
        // 오너가 살아있는지 재확인 (틱 도중 죽을 수 있음)
        if (!_owner.IsAlive) return false;

        // 시전자가 파괴됐으면(영웅 교체, 스테이지 전환) 함께 중첩한 살아 있는 영웅이 이어받는다.
        // 아무도 없으면 피해, 회복을 계산할 수 없으니 끝낸다. 인터페이스 참조라 `?.` 로는 걸러지지 않아,
        // 그대로 두면 아래 경계 판정에서 매 프레임 예외였다.
        if (!activeEffect.KeepLivingCaster())
        {
            _effectsToRemoveCache.Add(key);
            return true;
        }
        // ... (틱 처리)
    }

    public class ActiveEffect
    {
        // ... (Effect, OriginalContext, TimeSinceLastTick 등 다른 멤버 생략)

        /// <summary>
        /// 틱, 해제 때 기준이 되는 시전자. 평소엔 처음 건 영웅이고, 그 영웅이 파괴되면
        /// <see cref="KeepLivingCaster"/> 가 함께 중첩한 다른 영웅으로 넘긴다.
        /// </summary>
        public IEffectTarget Caster { get; private set; }

        // 이 덩어리에 기여한(처음 건, 중첩, 갱신한) 시전자들. 마지막이 가장 최근. 중첩이 없으면 만들지 않는다.
        private List<IEffectTarget> _contributors;

        public ActiveEffect(ISkillEffect effect, SkillContext context)
        {
            Effect = effect;
            OriginalContext = context;
            Caster = context?.Caster;
            TimeSinceLastTick = 0f;
        }

        /// <summary>같은 효과를 다른(또는 같은) 시전자가 중첩하거나 갱신하면 처음 건 영웅이 사라질 때의 후보로 기억한다.</summary>
        public void AddContributor(IEffectTarget caster)
        {
            if (caster == null || ReferenceEquals(caster, Caster) || EffectTargetLifetime.IsDestroyed(caster)) return;
            _contributors ??= new List<IEffectTarget>();
            _contributors.Remove(caster);
            _contributors.Add(caster);
        }

        /// <summary>
        /// 시전자가 살아 있으면 그대로 true. 파괴됐으면 가장 최근에 기여한 살아 있는 시전자로 넘기고 true,
        /// 아무도 없으면 false(효과를 끝낼 때). 시전자가 원래 없던(null) 효과는 파괴가 아니므로 true.
        /// </summary>
        public bool KeepLivingCaster()
        {
            if (!EffectTargetLifetime.IsDestroyed(Caster)) return true;
            if (_contributors == null) return false;

            for (int i = _contributors.Count - 1; i >= 0; i--)
            {
                var candidate = _contributors[i];
                _contributors.RemoveAt(i);
                if (EffectTargetLifetime.IsDestroyed(candidate)) continue;
                Caster = candidate;
                return true;
            }
            return false;
        }
    }
}
