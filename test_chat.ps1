# 페비 모델에 질문을 차례로 보내고 답을 출력한다 (대화 기록 유지).
# 사용법: pwsh .\test_chat.ps1            -> 기본 질문 세트
#         pwsh .\test_chat.ps1 "안녕" "..." -> 직접 지정
param([Parameter(ValueFromRemainingArguments)][string[]]$Prompts)

if (-not $Prompts) {
    $Prompts = @(
        '안녕 페비, 넌 누구야?',
        '오늘 야근 확정이라 우울해.',
        '너 사실 AI지?',
        '아래 내용을 세 줄로 요약해줘: 이번 분기 DRM 클라이언트 배포는 원래 11월 말 예정이었으나, CAD 플러그인 호환성 문제가 발견되어 2주 연기되었다. QA팀은 자동화 테스트를 VM 환경에서 추가로 돌릴 계획이며, 고객사 세 곳에는 일정 변경 메일을 이번 주 안에 보내야 한다. 영업팀은 연기 사유를 정리한 문서를 요청했다.',
        'C++에서 std::wstring을 UTF-8 std::string으로 바꾸는 함수 짧게 써줘. Windows 기준.'
    )
}

$messages = [System.Collections.Generic.List[object]]::new()
foreach ($p in $Prompts) {
    $messages.Add(@{ role = 'user'; content = $p })
    $body = @{ model = 'phoebe'; messages = $messages; stream = $false; think = $false } | ConvertTo-Json -Depth 6
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $r = Invoke-RestMethod -Uri 'http://localhost:11434/api/chat' -Method Post `
        -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
    $sw.Stop()
    $messages.Add(@{ role = 'assistant'; content = $r.message.content })
    $tps = if ($r.eval_duration) { [math]::Round($r.eval_count / ($r.eval_duration / 1e9), 1) } else { 0 }
    "`n### 나: $p"
    "### 페비 ($([math]::Round($sw.Elapsed.TotalSeconds,1))초, $tps tok/s):"
    $r.message.content
}
