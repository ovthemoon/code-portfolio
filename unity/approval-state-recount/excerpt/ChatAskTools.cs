// 발췌: 질문 도구를 작업 도구와 구분하는 목록 전체. 원본은 Unity 클라이언트 코드라 빌드에서 제외한다.
// namespace 를 걷어 냈고, 주석은 내부 파일 경로와 날짜를 일반화하고 정리했다.

using System;
using System.Collections.Generic;

/// <summary>
/// "유저에게 묻는" 도구. 도구이지만 작업이 아니다.
///
/// 라이브에는 <c>ActivityState.Working</c> 이 오지 않아 클라이언트가 도구 이벤트를 보고
/// 주입한다(<c>MarkToolActivity</c>). 그런데 질문 도구도 똑같이 `tool_event(start)` 를 내므로
/// 동료가 Working 상태가 되어 urgent(뛰기)로 HomeDesk 책상에 달려간다. 같은 순간 그 질문이
/// <c>tool_user_ask</c> 로 attention 을 켜서 손도 든다. 손을 들고 달려가는 것이다(사용자
/// 리포트). 질문은 그 자리에서 하는 게 맞고, 이미 앉아 있었다면 앉은 채로 물으면 된다.
///
/// 기준은 미들웨어(파이썬)의 질문 도구 이름 목록이다.
/// <c>ChatAskToolParityTests</c> 가 그 소스를 읽어 대조한다(손으로 복사한 목록이라
/// 주석만으로는 어긋난다).
/// </summary>
public static class ChatAskTools
{
    private static readonly HashSet<string> Names = new(StringComparer.Ordinal)
    {
        "ask_user", "ask_user_question", "select_options",
    };

    /// <summary>이 도구가 "유저 응답 대기"인가. 빈 이름은 false(미상 도구는 종전대로 작업 취급).</summary>
    public static bool IsAsk(string toolName)
        => !string.IsNullOrEmpty(toolName) && Names.Contains(toolName);
}
