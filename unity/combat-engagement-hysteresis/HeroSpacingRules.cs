using System;

namespace CodePortfolio.Unity.CombatEngagement
{
    /// <summary>
    /// 영웅끼리의 표적 분산 규칙. 원본 파일의 간격 유지와 진형 추종은 Unity 벡터에 의존해 여기서는 표적 점수만 둔다.
    /// 전원이 가장 가까운 적만 고르면 한 적에 셋 이상이 몰린다.
    /// </summary>
    public static class HeroSpacingRules
    {
        /// <summary>이미 그 적을 노리는 동료 1명당 거리에 더하는 벌점(m). 1~2m 차이면 빈 적으로 흩어진다.</summary>
        public const float CROWD_PENALTY_PER_ALLY = 2f;

        /// <summary>낮을수록 먼저 고른다.</summary>
        public static float TargetScore(float distance, int alliesOnTarget) =>
            distance + CROWD_PENALTY_PER_ALLY * Math.Max(0, alliesOnTarget);
    }
}
