using CodePortfolio.Unity.CombatEngagement;
using NUnit.Framework;

namespace CodePortfolio.Unity.Tests.CombatEngagement
{
    /// <summary>
    /// "모든 상태가 같은 계획을 쓴다"와 "들어가는 선과 나오는 선이 다르다"를 고정한다.
    /// </summary>
    [TestFixture]
    public class HeroEngagementRulesTests
    {
        private static readonly AttackOption Ready6 = new AttackOption(true, 6f);
        private static readonly AttackOption NotReady = new AttackOption(false, 6f);

        [Test]
        public void UltimateWithoutRange_UsesBasicAttackRange_NotStatRange()
        {
            // 궁극기 사거리는 미기입(0), 스탯 사거리는 기본공격과 무관한 값
            var ultimate = new AttackOption(true, 0f);
            var active = new AttackOption(false, 6f);

            var plan = HeroEngagementRules.Plan(ultimate, active, Ready6, statRange: 3.5f, autoUltimate: true);

            Assert.That(plan.Choice, Is.EqualTo(AttackChoice.Ultimate));
            Assert.That(plan.Range, Is.EqualTo(6f));
        }

        [Test]
        public void NothingReady_HoldsAtBasicAttackRange_NotStatRange()
        {
            // 쿨다운 사이에 스탯 사거리(15m)를 쓰면 '15m 면 사거리 안'으로 판정되던 값
            var basic = new AttackOption(false, 3f);

            var plan = HeroEngagementRules.Plan(NotReady, NotReady, basic, statRange: 15f, autoUltimate: true);

            Assert.That(plan.Choice, Is.EqualTo(AttackChoice.None));
            Assert.That(plan.Range, Is.EqualTo(3f));
        }

        [Test]
        public void StatRangeIsLastResort_WhenNoBasicAttackRange()
        {
            var plan = HeroEngagementRules.Plan(NotReady, NotReady, new AttackOption(false, 0f), statRange: 3.5f, autoUltimate: true);

            Assert.That(plan.Range, Is.EqualTo(3.5f));
        }

        [Test]
        public void Priority_UltimateThenActiveThenBasic()
        {
            var ultimate = new AttackOption(true, 5f);
            var active = new AttackOption(true, 12f);

            Assert.That(HeroEngagementRules.Plan(ultimate, active, Ready6, 2f, autoUltimate: true).Choice, Is.EqualTo(AttackChoice.Ultimate));
            Assert.That(HeroEngagementRules.Plan(ultimate, active, Ready6, 2f, autoUltimate: false).Choice, Is.EqualTo(AttackChoice.Active));
            Assert.That(HeroEngagementRules.Plan(NotReady, NotReady, Ready6, 2f, autoUltimate: true).Choice, Is.EqualTo(AttackChoice.Basic));
        }

        [Test]
        public void EnterAndLeaveLines_HaveGap_SoBoundaryDoesNotFlicker()
        {
            const float range = 6f;
            float justInside = range - 0.01f;

            // 사거리 경계 바로 안쪽에서는 전투 중이면 머무르고, 접근 중이면 아직 들어가지 않는다
            Assert.That(HeroEngagementRules.ShouldLeaveCombat(justInside, range), Is.False);
            Assert.That(HeroEngagementRules.ShouldEnterCombat(justInside, range), Is.False);
            Assert.That(HeroEngagementRules.ShouldEnterCombat(range - HeroEngagementRules.EnterMargin(range), range), Is.True);
            Assert.That(HeroEngagementRules.ShouldLeaveCombat(range + 0.01f, range), Is.True);
        }

        [TestCase(0.5f)]
        [TestCase(1f)]
        [TestCase(3f)]
        [TestCase(6f)]
        [TestCase(12f)]
        public void EnterLine_IsNeverOutsideLeaveLine(float range)
        {
            float enterLine = range - HeroEngagementRules.EnterMargin(range);

            Assert.That(enterLine, Is.LessThan(range));
            Assert.That(HeroEngagementRules.ShouldEnterCombat(enterLine, range), Is.True);
            Assert.That(HeroEngagementRules.ShouldLeaveCombat(enterLine, range), Is.False);
        }

        [Test]
        public void DistanceExactlyAtRange_NeitherEntersNorLeaves()
        {
            const float range = 6f;

            Assert.That(HeroEngagementRules.ShouldLeaveCombat(range, range), Is.False);
            Assert.That(HeroEngagementRules.ShouldEnterCombat(range, range), Is.False);
        }

        [Test]
        public void EnterMargin_ShrinksForShortMeleeRanges()
        {
            Assert.That(HeroEngagementRules.EnterMargin(1f), Is.LessThanOrEqualTo(0.2f + 1e-4f));
            Assert.That(HeroEngagementRules.EnterMargin(8f), Is.EqualTo(HeroEngagementRules.MAX_ENTER_MARGIN));
        }

        [Test]
        public void EnterMargin_NegativeRange_IsZero()
        {
            Assert.That(HeroEngagementRules.EnterMargin(-3f), Is.EqualTo(0f));
        }
    }
}
