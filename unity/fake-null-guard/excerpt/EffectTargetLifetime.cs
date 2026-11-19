// 발췌: 파괴된 Unity 오브젝트 판정 전체. 원본은 UnityEngine 에 의존해 빌드에서 제외한다.
// namespace 를 걷어 내고 주석을 정리했다.

using UnityEngine;

/// <summary>
/// <see cref="IEffectTarget"/> 가 이미 파괴됐는지 판정한다.
///
/// <para>엔티티는 MonoBehaviour 지만 효과, 투사체는 인터페이스(<see cref="IEffectTarget"/>)로 들고 있다.
/// 인터페이스 참조에는 Unity 의 파괴 판정(<c>== null</c> 오버로드)이 걸리지 않아, 파괴된 뒤에도
/// <c>caster?.GetTransform()</c> 의 <c>?.</c> 를 통과해 MissingReferenceException 을 던진다.
/// 시전자를 인터페이스로 들고 있다가 나중에 다시 읽는 곳(지속 효과 틱, 투사체)은 이 판정을 거친다.</para>
/// </summary>
public static class EffectTargetLifetime
{
    /// <summary>파괴된 Unity 오브젝트면 true. null(시전자 없음)은 파괴가 아니므로 false.</summary>
    public static bool IsDestroyed(IEffectTarget target) =>
        target is Object unityObject && unityObject == null;

    /// <summary>살아 있으면 transform, null 이거나 파괴됐으면 null. 파괴된 transform 은 읽지 않는다.</summary>
    public static Transform TransformOrNull(IEffectTarget target) =>
        target == null || IsDestroyed(target) ? null : target.GetTransform();
}
