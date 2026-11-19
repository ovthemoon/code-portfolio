// 발췌: 화면에 들어가기 전에 번역 표를 비동기로 미리 불러오는 함수. 원본은 UniTask 와 Unity Localization 에 의존해 빌드에서 제외한다.
// 클래스 설명 주석, using, namespace 는 생략하고 나머지 주석을 정리했다.

public static class LocTablePreloader
{
    /// <summary>Locale 변경으로 비워진 캐시를 씬 활성화 전에 채운다. 실패는 로더가 표시한다.</summary>
    public static async UniTask PreloadAllAsync(CancellationToken ct)
    {
        await LocalizationSettings.InitializationOperation.ToUniTask(cancellationToken: ct);
        await LocalizationSettings.StringDatabase.GetAllTables().ToUniTask(cancellationToken: ct);
    }

    public static async UniTask PreloadAsync(CancellationToken ct, params string[] tables)
    {
        if (tables == null || tables.Length == 0) return;
        try
        {
            await LocalizationSettings.InitializationOperation.ToUniTask(cancellationToken: ct);
            foreach (var table in tables)
            {
                if (string.IsNullOrEmpty(table)) continue;
                var op = LocalizationSettings.StringDatabase.GetTableAsync(table);
                await op.ToUniTask(cancellationToken: ct);
            }
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception e)
        {
            // 프리로드 실패는 치명적이지 않다. 진입은 계속하고, 동기 조회는 key 를 그대로 돌려주거나 재시도한다.
            Debug.LogWarning($"[LocTablePreloader] 테이블 프리로드 실패(계속): {e.Message}");
        }
    }
}
