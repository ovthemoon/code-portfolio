using System;
using System.Collections.Generic;
using CodePortfolio.Unity.CombatEngagement;
using NUnit.Framework;

namespace CodePortfolio.Unity.Tests.CombatEngagement
{
    /// <summary>
    /// 적이 사거리 경계에서 흔들릴 때 접근과 전투 상태가 몇 번 바뀌는지 센다.
    /// 들어가는 선과 나오는 선이 같은 규칙(기준선 하나)과 이 레포의 규칙(이중선)을 같은 거리 열로 비교한다.
    /// </summary>
    [TestFixture]
    public class EngagementFlickerTests
    {
        private enum Mode { Approach, Combat }

        private const float Range = 6f;
        private const int JitterSteps = 100;

        [Test]
        public void SingleBoundaryLine_FlipsOnEveryJitterStep()
        {
            int flips = CountFlips(Distances(), SingleLine);

            Assert.That(flips, Is.GreaterThanOrEqualTo(JitterSteps));
        }

        [Test]
        public void EnterLeaveGap_FlipsAtMostTwice_ForTheSameDistances()
        {
            int flips = CountFlips(Distances(), WithGap);

            Assert.That(flips, Is.LessThanOrEqualTo(2));
        }

        // 접근하다가 전투에 들어간 뒤, 적이 사거리 경계 0.1m 앞뒤로 번갈아 흔들린다.
        private static List<float> Distances()
        {
            var distances = new List<float> { 9f, 8f, 7f, 6.5f, 6f, Range - HeroEngagementRules.EnterMargin(Range) };
            for (int i = 0; i < JitterSteps; i++) distances.Add(i % 2 == 0 ? Range + 0.1f : Range - 0.1f);
            return distances;
        }

        private static Mode SingleLine(Mode current, float distance) =>
            distance <= Range ? Mode.Combat : Mode.Approach;

        private static Mode WithGap(Mode current, float distance)
        {
            if (current == Mode.Approach)
                return HeroEngagementRules.ShouldEnterCombat(distance, Range) ? Mode.Combat : Mode.Approach;
            return HeroEngagementRules.ShouldLeaveCombat(distance, Range) ? Mode.Approach : Mode.Combat;
        }

        private static int CountFlips(List<float> distances, Func<Mode, float, Mode> next)
        {
            var mode = Mode.Approach;
            int flips = 0;
            foreach (float distance in distances)
            {
                var updated = next(mode, distance);
                if (updated != mode) flips++;
                mode = updated;
            }
            return flips;
        }
    }
}
