using System;
using System.Linq;
using CodePortfolio.Unity.CombatEngagement;
using NUnit.Framework;

namespace CodePortfolio.Unity.Tests.CombatEngagement
{
    [TestFixture]
    public class HeroSpacingRulesTests
    {
        [Test]
        public void TargetScore_PrefersLessCrowdedEnemy_WhenDistancesAreClose()
        {
            // 한 적이 1m 더 가깝지만 이미 동료 둘이 붙어 있다
            float crowded = HeroSpacingRules.TargetScore(distance: 3f, alliesOnTarget: 2);
            float free = HeroSpacingRules.TargetScore(distance: 4f, alliesOnTarget: 0);

            Assert.That(free, Is.LessThan(crowded));
        }

        [Test]
        public void TargetScore_StillPicksNearby_OverFarAwayEmptyEnemy()
        {
            float crowded = HeroSpacingRules.TargetScore(distance: 2f, alliesOnTarget: 1);
            float farAway = HeroSpacingRules.TargetScore(distance: 8f, alliesOnTarget: 0);

            Assert.That(crowded, Is.LessThan(farAway));
        }

        [Test]
        public void TargetScore_TreatsNegativeAllyCountAsZero()
        {
            Assert.That(HeroSpacingRules.TargetScore(5f, -3), Is.EqualTo(5f));
        }

        [Test]
        public void FiveAllies_AreSpreadAcrossThreeEnemies_InsteadOfPilingOnTheNearest()
        {
            // 모든 동료에게 같은 거리로 보이는 적 셋
            float[] distances = { 3f, 4f, 5f };

            int[] nearestOnly = Assign(5, distances, (distance, crowd) => distance);
            int[] scored = Assign(5, distances, HeroSpacingRules.TargetScore);

            // 가장 가까운 적만 고르면 전원이 한 적에 몰리고, 점수에 동료 수를 넣으면 셋 이상 몰리지 않는다
            Assert.That(nearestOnly.Max(), Is.EqualTo(5));
            Assert.That(scored.Max(), Is.LessThan(3));
            Assert.That(scored.Sum(), Is.EqualTo(5));
        }

        // 동료가 차례로 점수가 가장 낮은 적을 고른다. 이미 고른 동료 수가 다음 동료의 점수에 반영된다.
        private static int[] Assign(int allies, float[] distances, Func<float, int, float> score)
        {
            var crowd = new int[distances.Length];
            for (int ally = 0; ally < allies; ally++)
            {
                int best = 0;
                for (int enemy = 1; enemy < distances.Length; enemy++)
                {
                    if (score(distances[enemy], crowd[enemy]) < score(distances[best], crowd[best])) best = enemy;
                }
                crowd[best]++;
            }
            return crowd;
        }
    }
}
