// 발췌: 전투 구역 카메라를 고정하는 Cinemachine 확장에서 Near 클립 상한을 두는 부분.
// 원본은 Cinemachine 과 Unity 에 의존해 빌드에서 제외한다. 생략한 부분은 ... 로 표시했다.

/// <summary>
/// Locks the view to the authored combat window: one rotation and one zoom (<see cref="GroupCombatBoundary.OrthoSize"/>),
/// including during camera blends. The camera centres on the virtual camera's Follow target, so character focus
/// (<c>CameraViewController</c>) keeps working; the default view follows the group, i.e. the window centre.
///
/// <para>It also caps the near clip plane at <see cref="MAX_NEAR_CLIP"/>. URP rebuilds the fog distance of toon stage
/// materials as <c>max((1 - clip.z / near) * far, 0)</c>, a formula that only holds for perspective depth. An orthographic
/// clip.z is linear in [0, 1], so a near plane of about 1 or more turns that distance into thousands of metres and the
/// whole stage is painted with the mood's fog colour, while a smaller near plane collapses it to 0 (no fog). The
/// character-focus preset asks for near 1.5, which is meaningless at this 75 m orthographic distance but blanked the map.</para>
/// </summary>
[DisallowMultipleComponent]
public sealed class GroupCombatCameraConstraint : CinemachineExtension
{
    /// <summary>
    /// Largest near clip plane the combat view may use. Must stay well below the smallest orthographic clip.z of
    /// anything on screen (about <c>1 - depth / far</c>, i.e. 0.98 at 75 m with the 5000 m far plane) so that the
    /// URP fog reconstruction above keeps returning 0. 0.3 is the "기본" preset's value, i.e. the look before this cap.
    /// </summary>
    public const float MAX_NEAR_CLIP = 0.3f;

    // ...

    protected override void PostPipelineStageCallback(CinemachineVirtualCameraBase vcam,
        CinemachineCore.Stage stage, ref CameraState state, float deltaTime)
    {
        // ... (회전과 위치 고정)
        var lens = state.Lens;
        lens.ModeOverride = LensSettings.OverrideModes.Orthographic;
        lens.OrthographicSize = boundary.OrthoSize;
        lens.NearClipPlane = Mathf.Min(lens.NearClipPlane, MAX_NEAR_CLIP);
        lens.Dutch = 0f;
        state.Lens = lens;
    }
}
