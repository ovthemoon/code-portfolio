using System;

namespace CodePortfolio.Unity.CombatEngagement
{
    /// <summary>다음에 쓸 공격 후보 하나. 지금 쓸 수 있는가, 사거리는 얼마인가(0 이하는 미기입).</summary>
    public readonly struct AttackOption
    {
        public readonly bool IsReady;
        public readonly float Range;

        public AttackOption(bool isReady, float range)
        {
            IsReady = isReady;
            Range = range;
        }
    }

    public enum AttackChoice { None, Ultimate, Active, Basic }

    /// <summary>다음 공격 계획. 무엇을 쓰고, 몇 m 안에 있어야 하는가.</summary>
    public readonly struct AttackPlan
    {
        public readonly AttackChoice Choice;
        public readonly float Range;

        public AttackPlan(AttackChoice choice, float range)
        {
            Choice = choice;
            Range = range;
        }
    }

    /// <summary>
    /// 영웅의 '다음 공격'과 그 사거리를 정하는 단일 규칙. 대기, 접근, 전투 상태가 전부 이것만 쓴다.
    /// 세 상태가 각자 다른 우선순위와 폴백으로 사거리를 재던 것이 경계에서 매 프레임 상태를 뒤집었다.
    /// 사거리가 비어 있는 스킬은 스탯 사거리가 아니라 기본공격 사거리를 따른다.
    /// 스탯 사거리는 캐릭터마다 기본공격과 무관하게 흩어져 있기 때문이다.
    /// </summary>
    public static class HeroEngagementRules
    {
        /// <summary>접근이 전투로 넘어가기 전에 사거리보다 더 들어가는 최대 여유(m).</summary>
        public const float MAX_ENTER_MARGIN = 0.4f;

        /// <summary>짧은 근접 사거리에서는 여유를 사거리의 이 비율로 줄인다.</summary>
        private const float ENTER_MARGIN_RATIO = 0.2f;

        public static AttackPlan Plan(AttackOption ultimate, AttackOption active, AttackOption basic, float statRange, bool autoUltimate)
        {
            float fallback = basic.Range > 0f ? basic.Range : statRange;

            if (autoUltimate && ultimate.IsReady) return new AttackPlan(AttackChoice.Ultimate, RangeOr(ultimate, fallback));
            if (active.IsReady) return new AttackPlan(AttackChoice.Active, RangeOr(active, fallback));
            if (basic.IsReady) return new AttackPlan(AttackChoice.Basic, fallback);
            return new AttackPlan(AttackChoice.None, fallback);
        }

        /// <summary>
        /// 접근에서 전투로 넘어가는 선. 사거리보다 조금 더 들어가야 넘어간다.
        /// 전투에서 접근으로 돌아가는 선(<see cref="ShouldLeaveCombat"/>)과 같으면
        /// 움직이는 적 앞에서 경계를 넘나들며 깜빡인다.
        /// </summary>
        public static bool ShouldEnterCombat(float distance, float range) => distance <= range - EnterMargin(range);

        /// <summary>전투에서 접근으로 돌아가는 선. 사거리를 벗어났을 때만.</summary>
        public static bool ShouldLeaveCombat(float distance, float range) => distance > range;

        public static float EnterMargin(float range) => Math.Min(MAX_ENTER_MARGIN, Math.Max(0f, range) * ENTER_MARGIN_RATIO);

        private static float RangeOr(AttackOption option, float fallback) => option.Range > 0f ? option.Range : fallback;
    }
}
