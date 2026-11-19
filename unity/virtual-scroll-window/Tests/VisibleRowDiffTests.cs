using System.Collections.Generic;
using CodePortfolio.Unity.VirtualScroll;
using NUnit.Framework;

namespace CodePortfolio.Unity.Tests.VirtualScroll
{
    [TestFixture]
    public class VisibleRowDiffTests
    {
        private readonly List<int> _toReturn = new List<int>();
        private readonly List<int> _toAcquire = new List<int>();

        [Test]
        public void FromNothing_AcquiresTheWholeRange()
        {
            VisibleRowDiff.Compute(new HashSet<int>(), new VisibleRange(0, 5), _toReturn, _toAcquire);

            Assert.That(_toReturn, Is.Empty);
            Assert.That(_toAcquire, Is.EqualTo(new[] { 0, 1, 2, 3, 4 }));
        }

        [Test]
        public void ScrollingByOneRow_ReturnsOneAndAcquiresOne()
        {
            var visible = new HashSet<int> { 0, 1, 2, 3, 4 };

            VisibleRowDiff.Compute(visible, new VisibleRange(1, 6), _toReturn, _toAcquire);

            Assert.That(_toReturn, Is.EqualTo(new[] { 0 }));
            Assert.That(_toAcquire, Is.EqualTo(new[] { 5 }));
        }

        [Test]
        public void SameRange_ChangesNothing()
        {
            var visible = new HashSet<int> { 3, 4, 5 };

            VisibleRowDiff.Compute(visible, new VisibleRange(3, 6), _toReturn, _toAcquire);

            Assert.That(_toReturn, Is.Empty);
            Assert.That(_toAcquire, Is.Empty);
        }

        [Test]
        public void JumpingFar_ReturnsAllOldRowsAndAcquiresAllNewRows()
        {
            var visible = new HashSet<int> { 0, 1, 2 };

            VisibleRowDiff.Compute(visible, new VisibleRange(500, 503), _toReturn, _toAcquire);

            Assert.That(_toReturn, Is.EquivalentTo(new[] { 0, 1, 2 }));
            Assert.That(_toAcquire, Is.EqualTo(new[] { 500, 501, 502 }));
        }

        [Test]
        public void ResultLists_AreClearedBeforeEachUse()
        {
            _toReturn.Add(99);
            _toAcquire.Add(99);

            VisibleRowDiff.Compute(new HashSet<int> { 1 }, new VisibleRange(1, 2), _toReturn, _toAcquire);

            Assert.That(_toReturn, Is.Empty);
            Assert.That(_toAcquire, Is.Empty);
        }

        [Test]
        public void ScrollingAThousandRows_NeverCreatesMoreRowsThanTheWindowHolds()
        {
            // 우편 1000개, 뷰포트 400, 행 간격 110, overscan 1. 풀에서 먼저 꺼내고 없을 때만 새로 만든다.
            const int count = 1000;
            const float viewport = 400f;
            const int windowBound = 7;
            var layout = new VirtualListLayout(100f, 10f, 20f, 20f, 1);
            var visible = new HashSet<int>();
            var pool = new Stack<int>();
            int created = 0;
            int acquired = 0;
            int largestVisibleSet = 0;

            // 맨 위에서 맨 아래까지 25px 씩 스크롤
            for (float scroll = 0f; scroll <= layout.ContentHeight(count); scroll += 25f)
            {
                var range = layout.Visible(scroll, viewport, count);
                VisibleRowDiff.Compute(visible, range, _toReturn, _toAcquire);

                foreach (int index in _toReturn)
                {
                    visible.Remove(index);
                    pool.Push(index);
                }

                foreach (int index in _toAcquire)
                {
                    if (pool.Count > 0) pool.Pop();
                    else created++;
                    acquired++;
                    visible.Add(index);
                }

                largestVisibleSet = System.Math.Max(largestVisibleSet, visible.Count);
            }

            // 만든 행 수는 창 크기에 묶이고, 목록 길이와 무관하다. 대부분은 재사용이다.
            Assert.That(largestVisibleSet, Is.LessThanOrEqualTo(windowBound));
            Assert.That(created, Is.LessThanOrEqualTo(windowBound));
            Assert.That(acquired, Is.GreaterThan(count - windowBound));
        }
    }
}
