// 발췌: 환경 카메라와 캐릭터 카메라를 합성하는 컴포넌트에서 카메라 동기화 시점을 정하는 부분.
// 원본은 Unity URP 카메라 스택에 의존해 빌드에서 제외한다. 생략한 부분은 ... 로 표시했다.

[DisallowMultipleComponent]
[RequireComponent(typeof(Camera))]
public sealed class EnvironmentLayerCompositor : MonoBehaviour
{
    // ... (필드: _environmentCamera, _characterCamera, _outputRect, _ready 등)

    private void OnEnable()
    {
        // ... (카메라 스택과 합성 재질 준비)
        _ready = true;
        ResizeTarget();
        SynchronizeCamera();
        RenderPipelineManager.beginCameraRendering += BeforeCameraRendering;
    }

    private void LateUpdate()
    {
        if (!_ready) return;
        if (_characterCamera == null) { enabled = false; return; }
        ResizeTarget();
        SynchronizeCamera();
    }

    // Sync only on the environment camera's turn: it renders first (character depth = env + 1), so the
    // character camera still gets this frame's pose. Rewriting the character camera inside its own
    // beginCameraRendering silently drops world-space UGUI (health bars, cutscene dim) from that camera.
    private void BeforeCameraRendering(ScriptableRenderContext context, Camera camera)
    {
        if (_ready && camera == _environmentCamera) SynchronizeCamera();
    }

    private void SynchronizeCamera()
    {
        _characterCamera.transform.SetPositionAndRotation(_environmentCamera.transform.position, _environmentCamera.transform.rotation);
        _characterCamera.orthographic = _environmentCamera.orthographic;
        _characterCamera.orthographicSize = _environmentCamera.orthographicSize;
        _characterCamera.fieldOfView = _environmentCamera.fieldOfView;
        _characterCamera.nearClipPlane = _environmentCamera.nearClipPlane;
        _characterCamera.farClipPlane = _environmentCamera.farClipPlane;
        _characterCamera.aspect = _environmentCamera.aspect;
        _characterCamera.rect = _outputRect;
        _characterCamera.projectionMatrix = _environmentCamera.projectionMatrix;
        _characterCamera.depth = _environmentCamera.depth + 1;
        _characterCamera.enabled = _environmentCamera.enabled;
    }

    private void OnDisable()
    {
        RenderPipelineManager.beginCameraRendering -= BeforeCameraRendering;
        // ...
    }
}
