using System;
using System.Numerics;

namespace CodePortfolio.Unity.DashStop
{
    /// <summary>
    /// 돌진이 이동 가능한 영역(전투 창). 원본은 Unity 컴포넌트이고, 여기서는 이 규칙에 필요한 한 동작만 인터페이스로 둔다.
    /// </summary>
    public interface ICombatWindow
    {
        /// <summary>start 에서 end 로 직선 이동할 때 창 안에서 멈출 수 있는 가장 먼 지점.</summary>
        Vector3 ClampAlong(Vector3 start, Vector3 end);
    }

    /// <summary>
    /// 돌진(목표 앞에서 멈추는 방식)이 실제로 이동할 거리를 계산하는 순수 규칙.
    /// "목표 중심에서 고정 0.5m 앞"이 아니라 <b>두 몸통(캡슐) 반지름 합 + 여유</b> 앞에서 멈춘다.
    /// 그렇지 않으면 몸통이 겹쳐 캐릭터 컨트롤러가 다음 물리 틱에 서로를 밀어낸다.
    /// 이미 그 거리 안이면 0. 억지로 최소 거리를 돌진해 파고들지 않는다.
    /// </summary>
    public static class DashStopDistance
    {
        /// <summary>몸통 접촉면과 멈춤 지점 사이 여유(m).</summary>
        public const float CONTACT_MARGIN = 0.1f;

        /// <summary>이 이하의 이동은 방향이 없는 것으로 보고 창 클램프를 건너뛴다(0 나눗셈 방지).</summary>
        private const float TRAVEL_EPSILON = 1e-4f;

        /// <param name="targetDistance">시전자 중심에서 목표 중심까지 거리</param>
        /// <param name="maxDistance">스킬에 설정된 최대 돌진 거리</param>
        /// <param name="casterRadius">시전자 캡슐 반지름(월드)</param>
        /// <param name="targetRadius">목표 캡슐 반지름(월드)</param>
        /// <returns>실제 돌진 거리. 0 이면 돌진 생략.</returns>
        public static float Compute(float targetDistance, float maxDistance, float casterRadius, float targetRadius)
        {
            float stopGap = Math.Max(0f, casterRadius) + Math.Max(0f, targetRadius) + CONTACT_MARGIN;
            float toStop = targetDistance - stopGap;
            if (toStop <= 0f) return 0f;
            return Math.Min(Math.Max(0f, maxDistance), toStop);
        }

        /// <summary>
        /// 돌진이 전투 창 밖으로 나가지 않도록 거리를 줄인다.
        /// 시전자가 창 밖이면 스킬을 끊는 규칙이 따로 있어서, 긴 돌진이 창 가장자리를 넘으면 도중에 끊긴다.
        /// 끊는 규칙은 그대로 두고 돌진이 가장자리에서 멈추게 한다. 경계가 없는 씬은 거리를 그대로 돌려준다.
        /// </summary>
        /// <param name="window">시전자 씬의 전투 창. null 이면 제한 없음.</param>
        /// <param name="direction">돌진 방향(<c>start + direction × distance</c> 로 이동한다)</param>
        /// <param name="distance">창을 고려하기 전 돌진 거리</param>
        /// <returns>창 안에서 갈 수 있는 거리. 0 이면 돌진 생략.</returns>
        public static float ClampToCombatWindow(ICombatWindow window, Vector3 start, Vector3 direction, float distance)
        {
            if (window == null || distance <= 0f) return distance;

            var end = start + direction * distance;
            float fullTravel = Vector3.Distance(start, end);
            if (fullTravel <= TRAVEL_EPSILON) return distance;

            float allowedTravel = Vector3.Distance(start, window.ClampAlong(start, end));
            return distance * Math.Min(1f, Math.Max(0f, allowedTravel / fullTravel));
        }
    }
}
