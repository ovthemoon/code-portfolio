using System.Collections.Generic;
using CodePortfolio.Unity.CombatEngagement;
using NUnit.Framework;

namespace CodePortfolio.Unity.Tests.CombatEngagement
{
    [TestFixture]
    public class HeroAttackPlannerTests
    {
        private static SkillSnapshot Basic(float range = 6f, bool canCast = true, float cooldown = 0f) =>
            new SkillSnapshot(SkillType.Basic, range, cooldown, canCast);

        private static SkillSnapshot Active(float range = 10f, bool canCast = true, float cooldown = 0f) =>
            new SkillSnapshot(SkillType.Active, range, cooldown, canCast);

        private static SkillSnapshot Ultimate(float range = 0f, bool canCast = true, float cooldown = 0f) =>
            new SkillSnapshot(SkillType.Ultimate, range, cooldown, canCast);

        [Test]
        public void ReadyUltimate_IsChosenFirst_WithBasicRangeWhenRangeIsEmpty()
        {
            var ultimate = Ultimate(range: 0f);
            var skills = new List<SkillSnapshot> { Active(), ultimate };

            var plan = HeroAttackPlanner.Plan(Basic(range: 6f), skills, statRange: 3.5f, autoUltimate: true, out var chosen);

            Assert.That(plan.Choice, Is.EqualTo(AttackChoice.Ultimate));
            Assert.That(plan.Range, Is.EqualTo(6f));
            Assert.That(chosen, Is.SameAs(ultimate));
        }

        [Test]
        public void UltimateThatCannotBeCastNow_DoesNotBlockTheBasicAttack()
        {
            // 쿨다운은 끝났지만 시전 조건이 안 맞는 궁극기
            var skills = new List<SkillSnapshot> { Ultimate(canCast: false, cooldown: 0f) };
            var basic = Basic();

            var plan = HeroAttackPlanner.Plan(basic, skills, statRange: 3.5f, autoUltimate: true, out var chosen);

            Assert.That(plan.Choice, Is.EqualTo(AttackChoice.Basic));
            Assert.That(chosen, Is.SameAs(basic));
        }

        [Test]
        public void ActiveSkillOnCooldown_IsSkipped()
        {
            var skills = new List<SkillSnapshot> { Active(cooldown: 3.5f) };

            var plan = HeroAttackPlanner.Plan(Basic(), skills, statRange: 3.5f, autoUltimate: true);

            Assert.That(plan.Choice, Is.EqualTo(AttackChoice.Basic));
        }

        [Test]
        public void BasicAttack_IgnoresCooldownField_AndFollowsCanCastNow()
        {
            // 기본공격의 공격 간격은 CanCastNow 가 판정한다. 쿨다운 값이 남아 있어도 그것만 본다.
            var ready = HeroAttackPlanner.Plan(Basic(canCast: true, cooldown: 1f), null, 3.5f, autoUltimate: true);
            var notReady = HeroAttackPlanner.Plan(Basic(canCast: false), null, 3.5f, autoUltimate: true);

            Assert.That(ready.Choice, Is.EqualTo(AttackChoice.Basic));
            Assert.That(notReady.Choice, Is.EqualTo(AttackChoice.None));
        }

        [Test]
        public void NothingReady_ReturnsNoSkill_AndHoldsAtBasicRange()
        {
            var plan = HeroAttackPlanner.Plan(Basic(range: 3f, canCast: false), new List<SkillSnapshot>(), statRange: 15f, autoUltimate: true, out var chosen);

            Assert.That(plan.Choice, Is.EqualTo(AttackChoice.None));
            Assert.That(plan.Range, Is.EqualTo(3f));
            Assert.That(chosen, Is.Null);
        }

        [Test]
        public void NullEntriesAndPassives_AreIgnored()
        {
            var skills = new List<SkillSnapshot>
            {
                null,
                new SkillSnapshot(SkillType.Passive, 99f, 0f, true),
            };

            var plan = HeroAttackPlanner.Plan(Basic(), skills, statRange: 3.5f, autoUltimate: true);

            Assert.That(plan.Choice, Is.EqualTo(AttackChoice.Basic));
            Assert.That(plan.Range, Is.EqualTo(6f));
        }

        [Test]
        public void NoSkillsAtAll_FallsBackToStatRange()
        {
            var plan = HeroAttackPlanner.Plan(null, null, statRange: 3.5f, autoUltimate: true);

            Assert.That(plan.Choice, Is.EqualTo(AttackChoice.None));
            Assert.That(plan.Range, Is.EqualTo(3.5f));
        }
    }
}
