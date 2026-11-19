using System;

namespace CodePortfolio.Unity.VirtualScroll
{
    /// <summary>화면에 만들어 둘 행의 반열린 구간 [First, End).</summary>
    public readonly struct VisibleRange
    {
        public readonly int First;
        public readonly int End;

        public VisibleRange(int first, int end)
        {
            First = first;
            End = end;
        }

        public int Count => End - First;

        public bool Contains(int index) => index >= First && index < End;
    }

    /// <summary>
    /// 높이가 고정된 행만 다룬다.
    /// 우편함 팝업의 보이는 행 계산을 Unity 레이아웃 컴포넌트에서 떼어 낸 순수 계산이다.
    /// 좌표는 모두 목록 맨 위에서 아래로 늘어나는 양수 오프셋이다.
    /// </summary>
    public readonly struct VirtualListLayout
    {
        public readonly float RowHeight;
        public readonly float Spacing;
        public readonly float PaddingTop;
        public readonly float PaddingBottom;
        public readonly int OverscanRows;

        /// <exception cref="ArgumentOutOfRangeException">
        /// 행 높이나 행 간격(높이 + 간격)이 0 이하이거나 overscan 이 음수일 때.
        /// 원본은 이 경우 가상 스크롤을 켜지 않고 일반 목록으로 남겼다.
        /// </exception>
        public VirtualListLayout(float rowHeight, float spacing, float paddingTop, float paddingBottom, int overscanRows)
        {
            if (rowHeight <= 0f) throw new ArgumentOutOfRangeException(nameof(rowHeight), "행 높이는 0보다 커야 한다.");
            if (rowHeight + spacing <= 0f) throw new ArgumentOutOfRangeException(nameof(spacing), "행 간격(높이 + 간격)은 0보다 커야 한다.");
            if (overscanRows < 0) throw new ArgumentOutOfRangeException(nameof(overscanRows), "overscan 은 0 이상이어야 한다.");

            RowHeight = rowHeight;
            Spacing = spacing;
            PaddingTop = paddingTop;
            PaddingBottom = paddingBottom;
            OverscanRows = overscanRows;
        }

        /// <summary>한 행이 차지하는 세로 길이(행 높이 + 간격).</summary>
        public float RowStride => RowHeight + Spacing;

        public float ContentHeight(int itemCount)
        {
            float rows = itemCount > 0 ? itemCount * RowHeight + (itemCount - 1) * Spacing : 0f;
            return PaddingTop + PaddingBottom + rows;
        }

        /// <summary>스크롤 위치를 [0, 내용 높이 - 뷰포트 높이] 안으로 자른다. 내용이 뷰포트보다 짧으면 0.</summary>
        public float ClampScroll(float scrollTop, int itemCount, float viewportHeight)
        {
            float maxScroll = Math.Max(0f, ContentHeight(itemCount) - viewportHeight);
            return Math.Min(Math.Max(scrollTop, 0f), maxScroll);
        }

        /// <summary>목록 맨 위에서 index 번째 행의 윗변까지 거리.</summary>
        public float RowTop(int index) => PaddingTop + index * RowStride;

        /// <summary>
        /// 뷰포트에 걸치는 행과 위아래 overscan 행의 구간.
        /// 위치가 내용 밖이거나 뷰포트 높이가 음수여도 0 &lt;= First &lt;= End &lt;= itemCount 를 지킨다.
        /// </summary>
        public VisibleRange Visible(float scrollTop, float viewportHeight, int itemCount)
        {
            float viewport = Math.Max(0f, viewportHeight);
            float top = ClampScroll(scrollTop, itemCount, viewport) - PaddingTop;

            int first = Math.Max(0, (int)Math.Floor(top / RowStride) - OverscanRows);
            int end = Math.Min(itemCount, (int)Math.Ceiling((top + viewport) / RowStride) + OverscanRows);
            first = Math.Min(first, end);
            return new VisibleRange(first, end);
        }
    }
}
