// 발췌: 우편함 팝업 클래스의 가상 스크롤 구간. 원본은 Unity UI 컴포넌트에 의존해 빌드에서 제외한다.
// 클래스 선언, 필드(_rowStride, _viewportRect, OVERSCAN_ROWS 등), 행 풀 반환 메서드는 생략했다.
// 보이는 행 계산(UpdateVisibleMailRows 의 first, end)을 순수 함수로 뗀 것이 ../VirtualListLayout.cs 이다.

private bool ConfigureVirtualList()
{
    if (_virtualListConfigured) return _usesVirtualList;
    _virtualListConfigured = true;
    _contentRect = _mailListContent as RectTransform;
    var rowRect = _mailItemPrefab.transform as RectTransform;
    if (_contentRect == null || rowRect == null) return false;
    _mailScrollRect = _contentRect.GetComponentInParent<ScrollRect>(true);
    if (_mailScrollRect == null || _mailScrollRect.content != _contentRect || !_mailScrollRect.vertical)
        return false;
    _mailListLayout = _contentRect.GetComponent<VerticalLayoutGroup>();
    // The shipped prefab uses fixed-height, unexpanded rows. A different authored
    // layout must not silently truncate text or change its row sizing.
    var rowFitter = rowRect.GetComponent<ContentSizeFitter>();
    if (_mailListLayout == null || !_mailListLayout.enabled ||
        _mailListLayout.childControlHeight || _mailListLayout.childForceExpandHeight ||
        _mailListLayout.childControlWidth || _mailListLayout.childForceExpandWidth || _mailListLayout.reverseArrangement ||
        (int)_mailListLayout.childAlignment >= 3 ||
        (rowFitter != null && rowFitter.enabled && rowFitter.verticalFit != ContentSizeFitter.FitMode.Unconstrained) ||
        rowRect.GetComponent<LayoutGroup>() != null || rowRect.localScale.y != 1f || rowRect.localScale.x != 1f)
        return false;

    _rowHeight = rowRect.rect.height;
    _rowWidth = rowRect.rect.width;
    _rowStride = _rowHeight + _mailListLayout.spacing;
    if (_rowHeight <= 0f || _rowStride <= 0f) return false;
    _viewportRect = _mailScrollRect.viewport != null
        ? _mailScrollRect.viewport : _mailScrollRect.transform as RectTransform;
    if (_viewportRect == null) return false;

    _mailListLayout.enabled = false;
    var fitter = _contentRect.GetComponent<ContentSizeFitter>();
    if (fitter != null) fitter.enabled = false;
    _contentRect.anchorMin = new Vector2(_contentRect.anchorMin.x, 1f);
    _contentRect.anchorMax = new Vector2(_contentRect.anchorMax.x, 1f);
    _contentRect.pivot = new Vector2(_contentRect.pivot.x, 1f);
    _usesVirtualList = true;
    RegisterScrollListener();
    return true;
}

private void RegisterScrollListener()
{
    if (_mailScrollRect == null || _scrollListenerRegistered) return;
    _mailScrollRect.onValueChanged.AddListener(OnMailScrollChanged);
    _scrollListenerRegistered = true;
}

private void OnMailScrollChanged(Vector2 position) => UpdateVisibleMailRows();

private void SetVirtualContentHeight()
{
    int count = _mailItems?.Count ?? 0;
    float height = _mailListLayout.padding.vertical +
        (count > 0 ? count * _rowHeight + (count - 1) * _mailListLayout.spacing : 0f);
    _contentRect.SetSizeWithCurrentAnchors(RectTransform.Axis.Vertical, height);
    var position = _contentRect.anchoredPosition;
    position.y = Mathf.Clamp(position.y, 0f, Mathf.Max(0f, height - _viewportRect.rect.height));
    _contentRect.anchoredPosition = position;
}

private void UpdateVisibleMailRows()
{
    if (!_usesVirtualList || _mailItems == null || !isActiveAndEnabled) return;
    _viewportHeight = _viewportRect.rect.height;
    _viewportWidth = _viewportRect.rect.width;
    float scrollTop = Mathf.Clamp(_contentRect.anchoredPosition.y, 0f,
        Mathf.Max(0f, _contentRect.rect.height - _viewportHeight));
    float listTop = scrollTop - _mailListLayout.padding.top;
    int first = Mathf.Max(0, Mathf.FloorToInt(listTop / _rowStride) - OVERSCAN_ROWS);
    int end = Mathf.Min(_mailItems.Count,
        Mathf.CeilToInt((listTop + Mathf.Max(0f, _viewportHeight)) / _rowStride) + OVERSCAN_ROWS);
    first = Mathf.Min(first, end);

    _rowsToReturn.Clear();
    foreach (var pair in _visibleMailRows)
        if (pair.Key < first || pair.Key >= end) _rowsToReturn.Add(pair.Key);
    foreach (int index in _rowsToReturn)
    {
        var row = _visibleMailRows[index];
        _visibleMailRows.Remove(index);
        _spawnedMailItems.Remove(row);
        ReturnMailRow(row);
    }

    for (int index = first; index < end; index++)
    {
        if (!_visibleMailRows.TryGetValue(index, out var row))
        {
            row = _mailItemPool.Count > 0 ? _mailItemPool.Pop() : Instantiate(_mailItemPrefab, _mailListContent);
            _visibleMailRows.Add(index, row);
            _spawnedMailItems.Add(row);
            row.Init(_mailItems[index], GetMailItemClickCallback());
            row.gameObject.SetActive(true);
        }
        PositionVirtualRow((RectTransform)row.transform, index);
        row.transform.SetSiblingIndex(index - first);
    }
}

private void PositionVirtualRow(RectTransform row, int index)
{
    row.anchorMin = new Vector2(0f, 1f);
    row.anchorMax = new Vector2(0f, 1f);
    row.pivot = new Vector2(0f, 1f);
    float availableWidth = _contentRect.rect.width - _mailListLayout.padding.horizontal;
    row.SetSizeWithCurrentAnchors(RectTransform.Axis.Horizontal, _rowWidth);
    row.SetSizeWithCurrentAnchors(RectTransform.Axis.Vertical, _rowHeight);
    float alignment = (int)_mailListLayout.childAlignment * 0.5f;
    row.anchoredPosition = new Vector2(_mailListLayout.padding.left + (availableWidth - _rowWidth) * alignment,
        -(_mailListLayout.padding.top + index * _rowStride));
}

private void LateUpdate()
{
    if (_usesVirtualList && (_viewportRect.rect.height != _viewportHeight || _viewportRect.rect.width != _viewportWidth))
    {
        SetVirtualContentHeight();
        UpdateVisibleMailRows();
    }
}
