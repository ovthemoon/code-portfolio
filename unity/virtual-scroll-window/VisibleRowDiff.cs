using System.Collections.Generic;

namespace CodePortfolio.Unity.VirtualScroll
{
    /// <summary>
    /// 지금 만들어 둔 행과 새로 보여야 할 구간을 비교해, 풀로 돌려보낼 행과 새로 꺼낼 행을 구한다.
    /// 호출자가 결과 리스트를 재사용하므로 스크롤 중에 할당이 생기지 않는다.
    /// </summary>
    public static class VisibleRowDiff
    {
        public static void Compute(HashSet<int> visible, VisibleRange target, List<int> toReturn, List<int> toAcquire)
        {
            toReturn.Clear();
            toAcquire.Clear();

            foreach (int index in visible)
            {
                if (!target.Contains(index)) toReturn.Add(index);
            }

            for (int index = target.First; index < target.End; index++)
            {
                if (!visible.Contains(index)) toAcquire.Add(index);
            }
        }
    }
}
