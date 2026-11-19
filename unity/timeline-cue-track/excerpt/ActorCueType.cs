// 발췌: 배우에게 내리는 큐의 종류(enum 만). 같은 파일의 PlayableAsset 클래스는 에디터 확장 라이브러리(Odin)를 써서 싣지 않는다.
// 원본은 Unity Timeline 에 의존해 빌드에서 제외한다. 주석은 정리했다.

public enum ActorCueType
{
    Walk,       // WalkTarget 지점으로 걷기 (기존 locomotion/A*, 도착 시각은 이동거리에 따름)
    Sit,        // 홈 책상으로 이동해 착석 (DeskChairController 경유)
    HudState,   // HUD 핀 상태/문구. 다음 HudState 큐까지 유지
    Expression, // 얼굴 표정 (Face 채널, 클립 길이만큼 유지 후 Default 복귀)
    Gesture,    // 상반신 제스처/포즈 (Body 채널, Typing/wave/thinking 등)
    // 아래는 반드시 끝에만 추가할 것. enum 은 int 로 직렬화되므로 중간 삽입은
    // 기존 클립의 Type 을 통째로 밀어버린다.
    FaceCamera, // 몸을 카메라 쪽으로 회전(큐 시점의 카메라 방향을 고정). Walk/Sit 큐가 해제
    FaceActor,  // FaceTarget 배우 쪽으로 회전. 착석 중이면 의자도 따라 돈다
    Speech,     // 머리 위 말풍선. 클립 길이만큼 표시(빈 문자열이면 즉시 지움)
}
