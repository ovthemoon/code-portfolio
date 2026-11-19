using System;
using CodePortfolio.Unity.VirtualScroll;
using NUnit.Framework;

namespace CodePortfolio.Unity.Tests.VirtualScroll
{
    [TestFixture]
    public class VirtualListLayoutTests
    {
        // 행 높이 100, 간격 10(행 간격 110), 위아래 여백 20, overscan 1
        private static VirtualListLayout Layout(int overscan = 1) => new VirtualListLayout(100f, 10f, 20f, 20f, overscan);

        [Test]
        public void ContentHeight_IsPaddingPlusRowsAndGaps()
        {
            // 1000 * 100 + 999 * 10 + 40
            Assert.That(Layout().ContentHeight(1000), Is.EqualTo(110030f));
        }

        [Test]
        public void ContentHeight_WithoutItems_IsOnlyPadding()
        {
            Assert.That(Layout().ContentHeight(0), Is.EqualTo(40f));
        }

        [Test]
        public void RowTop_StartsAfterPadding_AndAdvancesByStride()
        {
            Assert.That(Layout().RowTop(0), Is.EqualTo(20f));
            Assert.That(Layout().RowTop(3), Is.EqualTo(20f + 3 * 110f));
        }

        [Test]
        public void Visible_AtTop_StartsAtZero_AndAddsOverscanBelowOnly()
        {
            var range = Layout().Visible(scrollTop: 0f, viewportHeight: 400f, itemCount: 1000);

            // 뷰포트에 걸치는 행은 0~3, 아래쪽 overscan 1행
            Assert.That(range.First, Is.EqualTo(0));
            Assert.That(range.End, Is.EqualTo(5));
        }

        [Test]
        public void Visible_InTheMiddle_AddsOverscanOnBothSides()
        {
            var range = Layout().Visible(scrollTop: 1100f, viewportHeight: 400f, itemCount: 1000);

            Assert.That(range.First, Is.EqualTo(8));
            Assert.That(range.End, Is.EqualTo(15));
        }

        [Test]
        public void Visible_WithoutOverscan_IsOnlyTheRowsTouchingTheViewport()
        {
            var range = Layout(overscan: 0).Visible(scrollTop: 1100f, viewportHeight: 400f, itemCount: 1000);

            Assert.That(range.First, Is.EqualTo(9));
            Assert.That(range.End, Is.EqualTo(14));
        }

        [Test]
        public void Visible_WithNoItems_IsEmpty()
        {
            var range = Layout().Visible(0f, 400f, itemCount: 0);

            Assert.That(range.Count, Is.EqualTo(0));
            Assert.That(range.First, Is.EqualTo(0));
        }

        [Test]
        public void Visible_ScrolledPastTheEnd_ClampsToTheLastRows()
        {
            var range = Layout().Visible(scrollTop: 1e9f, viewportHeight: 400f, itemCount: 1000);

            Assert.That(range.End, Is.EqualTo(1000));
            Assert.That(range.First, Is.EqualTo(995));
        }

        [Test]
        public void Visible_OverscrolledAboveTheTop_BehavesLikeTop()
        {
            var top = Layout().Visible(0f, 400f, 1000);
            var bounced = Layout().Visible(-250f, 400f, 1000);

            Assert.That(bounced.First, Is.EqualTo(top.First));
            Assert.That(bounced.End, Is.EqualTo(top.End));
        }

        [Test]
        public void Visible_ContentShorterThanViewport_ShowsEverything()
        {
            var range = Layout().Visible(scrollTop: 300f, viewportHeight: 1000f, itemCount: 3);

            Assert.That(range.First, Is.EqualTo(0));
            Assert.That(range.End, Is.EqualTo(3));
        }

        [TestCase(0f)]
        [TestCase(50f)]
        [TestCase(400f)]
        [TestCase(5000f)]
        [TestCase(-10f)]
        public void Visible_NeverLeavesTheItemBounds(float viewportHeight)
        {
            const int count = 200;
            var layout = Layout();

            for (float scroll = -500f; scroll < layout.ContentHeight(count) + 500f; scroll += 37f)
            {
                var range = layout.Visible(scroll, viewportHeight, count);

                Assert.That(range.First, Is.GreaterThanOrEqualTo(0));
                Assert.That(range.First, Is.LessThanOrEqualTo(range.End));
                Assert.That(range.End, Is.LessThanOrEqualTo(count));
            }
        }

        [TestCase(0)]
        [TestCase(1)]
        [TestCase(2)]
        public void Visible_ContainsEveryRowThatTouchesTheViewport(int overscan)
        {
            // 모든 행의 위치를 직접 계산해 보이는 행이 하나도 빠지지 않는지 본다
            const int count = 200;
            const float viewport = 400f;
            var layout = Layout(overscan);

            for (float scroll = 0f; scroll <= layout.ContentHeight(count); scroll += 53f)
            {
                float clamped = layout.ClampScroll(scroll, count, viewport);
                var range = layout.Visible(scroll, viewport, count);

                for (int index = 0; index < count; index++)
                {
                    float rowTop = layout.RowTop(index);
                    float rowBottom = rowTop + layout.RowHeight;
                    bool touchesViewport = rowBottom > clamped && rowTop < clamped + viewport;
                    if (touchesViewport)
                        Assert.That(range.Contains(index), Is.True, $"scroll={scroll}, row={index}, overscan={overscan}");
                }
            }
        }

        [Test]
        public void Visible_RowCountIsBounded_RegardlessOfItemCount()
        {
            // 뷰포트 400, 행 간격 110, overscan 1: 걸치는 행은 최대 ceil(400/110) + 1 = 5, overscan 양쪽 2
            var layout = Layout();

            for (float scroll = 0f; scroll < layout.ContentHeight(100000); scroll += 977f)
                Assert.That(layout.Visible(scroll, 400f, 100000).Count, Is.LessThanOrEqualTo(7));
        }

        [Test]
        public void ClampScroll_StaysInsideContent()
        {
            var layout = Layout();

            Assert.That(layout.ClampScroll(-5f, 1000, 400f), Is.EqualTo(0f));
            Assert.That(layout.ClampScroll(1e9f, 1000, 400f), Is.EqualTo(110030f - 400f));
            Assert.That(layout.ClampScroll(500f, 1000, 400f), Is.EqualTo(500f));
        }

        [Test]
        public void Constructor_RejectsLayoutsThatCannotBeVirtualized()
        {
            Assert.Throws<ArgumentOutOfRangeException>(() => new VirtualListLayout(0f, 10f, 0f, 0f, 1));
            Assert.Throws<ArgumentOutOfRangeException>(() => new VirtualListLayout(100f, -100f, 0f, 0f, 1));
            Assert.Throws<ArgumentOutOfRangeException>(() => new VirtualListLayout(100f, 0f, 0f, 0f, -1));
        }
    }
}
