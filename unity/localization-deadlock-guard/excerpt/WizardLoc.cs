// 발췌: 위저드 화면용 번역 조회 함수. 원본은 Unity Localization 패키지에 의존해 빌드에서 제외한다.
// 클래스의 다른 멤버(IsReady 등)와 using, namespace 는 생략하고 주석을 정리했다.

public static class WizardLoc
{
    /// <summary>지정 String Table 에서 key 를 조회한다. 준비 전이거나 키가 없으면 key 를 그대로 돌려준다.</summary>
    public static string T(string table, string key)
    {
        if (string.IsNullOrEmpty(key)) return key;
        try
        {
            if (!IsReady) return key;
            // 테이블이 로드돼 있을 때만 조회한다. GetLocalizedString 은 미로드 테이블을
            // 동기 로드(WaitForCompletion)하며 그대로 메인 스레드 데드락이므로 절대 밟지
            // 않는다. GetTableAsync 는 캐시된 핸들을 돌려주고(이미 로드면 IsDone 즉시 true),
            // 미로드면 로드를 시작만 하고 이번 조회는 key 를 그대로 돌려준다(클릭 재빌드 경로는
            // 다음 호출에서 스스로 복구된다). 진입점(Opener/Onboarding)이 씬 로드 전에
            // 프리로드하므로 정상 흐름에선 항상 IsDone 이다.
            var op = LocalizationSettings.StringDatabase.GetTableAsync(table);
            if (!op.IsDone || op.Result == null) return key;
            var entry = op.Result.GetEntry(key);
            var v = entry?.GetLocalizedString();
            return string.IsNullOrEmpty(v) ? key : v;
        }
        catch { return key; }
    }

    // ...
}
