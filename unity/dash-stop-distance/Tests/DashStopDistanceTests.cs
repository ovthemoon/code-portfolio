using System.Numerics;
using CodePortfolio.Unity.DashStop;
using NUnit.Framework;

namespace CodePortfolio.Unity.Tests.DashStop
{
    /// <summary>
    /// 돌진 멈춤 거리 규칙. 몸통 반지름 합 앞에서 멈추고, 이미 가까우면 돌진하지 않는다.
    /// </summary>
    [TestFixture]
    public class DashStopDistanceTests
    {
        private const float Tolerance = 1e-4f;
        private const float CasterRadius = 0.4f;
        private const float TargetRadius = 0.3f;
        private const float StopGap = CasterRadius + TargetRadius + DashStopDistance.CONTACT_MARGIN;
        private const float MaxDash = 4f;
        private const float WindowDash = 7f;

        [Test]
        public void Compute_StopsBeforeCapsulesTouch()
        {
            const float targetDistance = 2f;

            float dash = DashStopDistance.Compute(targetDistance, MaxDash, CasterRadius, TargetRadius);

            // 멈춘 뒤 두 몸통 사이 간격이 정확히 여유값이다
            float gapAfterDash = targetDistance - dash - CasterRadius - TargetRadius;
            Assert.That(gapAfterDash, Is.EqualTo(DashStopDistance.CONTACT_MARGIN).Within(Tolerance));
        }

        [Test]
        public void Compute_DoesNotForceAMinimumDash_ThatWouldOverlapTheBodies()
        {
            // 최소 1m 이동을 강제하면 1.2m 거리에서 1.0m 를 돌진해 목표 중심 0.2m 앞까지 파고들고, 몸통이 겹친다.
            float dash = DashStopDistance.Compute(1.2f, MaxDash, CasterRadius, TargetRadius);

            Assert.That(dash, Is.LessThan(1.0f));
        }

        [Test]
        public void Compute_AlreadyInsideStopGap_ReturnsZero()
        {
            Assert.That(DashStopDistance.Compute(StopGap - 0.1f, MaxDash, CasterRadius, TargetRadius),
                Is.EqualTo(0f).Within(Tolerance));
            // 정확히 접촉 + 여유 거리
            Assert.That(DashStopDistance.Compute(StopGap, MaxDash, CasterRadius, TargetRadius),
                Is.EqualTo(0f).Within(Tolerance));
        }

        [Test]
        public void Compute_IsCappedByMaxDistance()
        {
            Assert.That(DashStopDistance.Compute(10f, MaxDash, CasterRadius, TargetRadius),
                Is.EqualTo(MaxDash).Within(Tolerance));
        }

        [Test]
        public void Compute_NegativeMaxDistance_IsTreatedAsZero()
        {
            Assert.That(DashStopDistance.Compute(10f, -MaxDash, CasterRadius, TargetRadius),
                Is.EqualTo(0f).Within(Tolerance));
        }

        [Test]
        public void Compute_NegativeRadiiTreatedAsZero()
        {
            float expected = 2f - DashStopDistance.CONTACT_MARGIN;

            Assert.That(DashStopDistance.Compute(2f, 5f, -1f, -1f), Is.EqualTo(expected).Within(Tolerance));
        }

        [Test]
        public void ClampToCombatWindow_NoWindow_ReturnsDistanceUnchanged()
        {
            float clamped = DashStopDistance.ClampToCombatWindow(null, Vector3.Zero, Vector3.UnitX, WindowDash);

            Assert.That(clamped, Is.EqualTo(WindowDash));
        }

        [Test]
        public void ClampToCombatWindow_StopsAtTheWindowEdge()
        {
            // x 가 10 을 넘으면 창 밖이다. 6 에서 출발해 7m 돌진하면 4m 에서 가장자리에 닿는다.
            var window = new WallWindow(maxX: 10f);
            var start = new Vector3(6f, 0f, 0f);

            float clamped = DashStopDistance.ClampToCombatWindow(window, start, Vector3.UnitX, WindowDash);

            Assert.That(clamped, Is.EqualTo(4f).Within(Tolerance));
        }

        [Test]
        public void ClampToCombatWindow_DashInsideTheWindow_IsNotShortened()
        {
            var window = new WallWindow(maxX: 100f);

            float clamped = DashStopDistance.ClampToCombatWindow(window, Vector3.Zero, Vector3.UnitX, WindowDash);

            Assert.That(clamped, Is.EqualTo(WindowDash).Within(Tolerance));
        }

        [Test]
        public void ClampToCombatWindow_AlreadyAtTheEdge_SkipsTheDash()
        {
            var window = new WallWindow(maxX: 10f);
            var start = new Vector3(10f, 0f, 0f);

            float clamped = DashStopDistance.ClampToCombatWindow(window, start, Vector3.UnitX, WindowDash);

            Assert.That(clamped, Is.EqualTo(0f).Within(Tolerance));
        }

        [Test]
        public void ClampToCombatWindow_ZeroOrNegativeDistance_ReturnedAsIs()
        {
            var window = new WallWindow(maxX: 10f);

            Assert.That(DashStopDistance.ClampToCombatWindow(window, Vector3.Zero, Vector3.UnitX, 0f), Is.EqualTo(0f));
            Assert.That(DashStopDistance.ClampToCombatWindow(window, Vector3.Zero, Vector3.UnitX, -2f), Is.EqualTo(-2f));
        }

        [Test]
        public void ClampToCombatWindow_ZeroDirection_ReturnsDistanceWithoutDividingByZero()
        {
            var window = new WallWindow(maxX: 10f);

            float clamped = DashStopDistance.ClampToCombatWindow(window, Vector3.Zero, Vector3.Zero, 5f);

            Assert.That(clamped, Is.EqualTo(5f));
        }

        // x 축에 벽이 하나 있는 창. 출발점이 벽 밖이면 그 자리에 둔다.
        private sealed class WallWindow : ICombatWindow
        {
            private readonly float _maxX;

            public WallWindow(float maxX) => _maxX = maxX;

            public Vector3 ClampAlong(Vector3 start, Vector3 end)
            {
                if (start.X > _maxX) return start;
                if (end.X <= _maxX) return end;
                float fraction = (_maxX - start.X) / (end.X - start.X);
                return Vector3.Lerp(start, end, fraction);
            }
        }
    }
}
