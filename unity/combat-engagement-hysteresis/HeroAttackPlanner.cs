using System.Collections.Generic;

namespace CodePortfolio.Unity.CombatEngagement
{
    public enum SkillType { Basic, Active, Ultimate, Passive }

    /// <summary>
    /// 스킬 하나의 현재 상태를 계획에 필요한 값만 담아 복사한 것.
    /// 원본은 스킬 객체와 스킬 컨트롤러를 직접 읽는다. 여기서는 Unity 의존을 걷어 값으로 받는다.
    /// </summary>
    public sealed class SkillSnapshot
    {
        public SkillType Type { get; }
        public float Range { get; }
        public float CooldownRemaining { get; }
        public bool CanCastNow { get; }

        public SkillSnapshot(SkillType type, float range, float cooldownRemaining, bool canCastNow)
        {
            Type = type;
            Range = range;
            CooldownRemaining = cooldownRemaining;
            CanCastNow = canCastNow;
        }
    }

    /// <summary>
    /// 영웅의 현재 스킬 상태를 <see cref="HeroEngagementRules"/> 에 넣어 '다음 공격'을 정한다.
    /// 대기, 접근, 전투 상태가 같은 프레임에 같은 답을 받도록 이 한 곳만 거친다.
    /// </summary>
    public static class HeroAttackPlanner
    {
        public static AttackPlan Plan(SkillSnapshot basic, IReadOnlyList<SkillSnapshot> skills, float statRange, bool autoUltimate)
            => Plan(basic, skills, statRange, autoUltimate, out _);

        public static AttackPlan Plan(SkillSnapshot basic, IReadOnlyList<SkillSnapshot> skills, float statRange, bool autoUltimate, out SkillSnapshot skill)
        {
            SkillSnapshot active = null;
            SkillSnapshot ultimate = null;
            if (skills != null)
            {
                foreach (var s in skills)
                {
                    if (s == null) continue;
                    if (s.Type == SkillType.Active) active = s;
                    else if (s.Type == SkillType.Ultimate) ultimate = s;
                }
            }

            var plan = HeroEngagementRules.Plan(
                Option(ultimate, needsCooldown: true),
                Option(active, needsCooldown: true),
                Option(basic, needsCooldown: false),
                statRange,
                autoUltimate);

            skill = plan.Choice switch
            {
                AttackChoice.Ultimate => ultimate,
                AttackChoice.Active => active,
                AttackChoice.Basic => basic,
                _ => null
            };
            return plan;
        }

        // 기본공격은 공격 간격을 CanCastNow 가 판정한다. 액티브와 궁극기는 쿨다운이 별도라 함께 본다.
        // 궁극기는 CanCastNow 로 시전이 거절될 조건까지 본다. 조건 미충족 궁극기에 묶여 기본공격도 안 하던 것을 막는다.
        private static AttackOption Option(SkillSnapshot skill, bool needsCooldown)
        {
            if (skill == null) return new AttackOption(false, 0f);
            bool ready = (!needsCooldown || skill.CooldownRemaining <= 0f) && skill.CanCastNow;
            return new AttackOption(ready, skill.Range);
        }
    }
}
