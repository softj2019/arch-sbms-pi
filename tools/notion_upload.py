import json
import urllib.request
import urllib.error

TOKEN = "ntn_n317044426760AV5TCkY5Ujpg8D6Oy4F9XN71cilSc30YM"
PAGE_ID = "3570bcf923eb801bb1b0fba2fe05936f"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

def api(method, path, data=None):
    url = f"https://api.notion.com/v1{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)

def t(text):
    return {"type": "text", "text": {"content": text}}

def h1(text):
    return {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [t(text)]}}

def h2(text):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t(text)]}}

def h3(text):
    return {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [t(text)]}}

def p(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [t(text)] if text else []}}

def divider():
    return {"object": "block", "type": "divider", "divider": {}}

def callout(text, emoji="📋"):
    return {"object": "block", "type": "callout", "callout": {
        "rich_text": [t(text)], "icon": {"type": "emoji", "emoji": emoji}
    }}

def code(text):
    return {"object": "block", "type": "code", "code": {
        "rich_text": [t(text)], "language": "plain text"
    }}

def make_table(headers, rows):
    children = []
    header_row = {"type": "table_row", "table_row": {"cells": [
        [{"type": "text", "text": {"content": c}, "annotations": {"bold": True}}] for c in headers
    ]}}
    children.append(header_row)
    for row in rows:
        children.append({"type": "table_row", "table_row": {"cells": [
            [{"type": "text", "text": {"content": c}}] for c in row
        ]}})
    return {
        "object": "block", "type": "table",
        "table": {
            "table_width": len(headers),
            "has_column_header": True,
            "has_row_header": False,
            "children": children
        }
    }

blocks = [
    h1("교통약자 스마트 버스 승강장 시스템 (SBMS) 안내"),
    callout("대상 독자: 현장 운영자, 관리자, 프레젠테이션 참석자\n목적: 교통약자 감지 및 승차대기 알림 시스템의 동작 원리를 쉽게 이해할 수 있도록 설명합니다.", "📋"),
    divider(),

    h2("📌 시스템 한눈에 보기"),
    p("SBMS는 버스 승강장에서 휠체어·목발 사용자를 자동으로 감지하고, 버스 기사에게 LED 전광판으로 알림을 보내는 스마트 시스템입니다."),
    code("[카메라 + 레이더]\n      ↓\n  [AI 분석]  <- 휠체어·목발 사용자 인식\n      ↓\n[중앙 제어 장치]\n      ↓\n[LED 전광판]  <- 버스 기사에게 교통약자 승차대기 알림\n      ↓\n  [서버 연동]  <- 관리 센터 실시간 모니터링"),
    h3("핵심 기능 요약"),
    make_table(
        ["기능", "설명"],
        [
            ["교통약자 감지", "카메라 AI가 휠체어·목발 사용자를 자동 식별"],
            ["승차대기 알림", "LED 전광판에 교통약자 승차대기 메시지 표시"],
            ["버스 기사 안내", "정류장 접근 전 사전 준비 가능"],
            ["원격 모니터링", "관리 서버에서 실시간 상황 확인"],
            ["오탐 방지", "배경 물체·벽 등 잘못된 감지를 AI가 자동 필터링"],
        ]
    ),
    divider(),

    h2("🎯 교통약자 감지 워크플로우"),
    h3("전체 흐름"),
    code("1. 카메라가 촬영\n      ↓\n2. AI 모델 1 (사람 감지)\n   사람·자전거·오토바이 인식 (휠체어 사용자 포함)\n      ↓\n3. AI 모델 2 (교통약자 전용)\n   휠체어 / 목발 인식\n      ↓\n4. 동시 감지 확인\n   사람 + 교통약자 기기 -> 유효한 감지\n   교통약자 기기만        -> 오탐으로 무시\n      ↓\n5. 면적 필터 (오탐 방지)\n   화면의 20% 이하 -> 통과 (실제 사람 크기)\n   화면의 20% 초과 -> 배경 물체로 판단, 무시\n      ↓\n6. 감지 확정 -> LED 알림 + 서버 전송"),
    h3("AI 이중 모델 구조"),
    callout("왜 AI 모델을 두 개 사용하나요?\n하나의 AI 모델만 사용하면 일반 자전거나 오토바이를 교통약자로 잘못 감지할 수 있습니다. 두 모델을 동시에 사용하여 사람이 있고, 그 사람이 교통약자 기기를 사용하는 경우만 알림을 보냅니다.", "💡"),
    make_table(
        ["AI 모델", "역할", "감지 대상"],
        [
            ["범용 모델 (COCO)", "사람 존재 여부 확인", "사람, 자전거, 오토바이"],
            ["전용 모델 (교통약자)", "기기 종류 식별", "휠체어, 목발"],
        ]
    ),
    h3("오탐 방지 로직"),
    p("화면 전체 면적 대비 감지 객체 크기로 배경 오탐을 필터링합니다."),
    make_table(
        ["감지 대상", "화면 점유율", "판정"],
        [
            ["실제 휠체어 사용자", "약 9~10%", "유효 — 통과"],
            ["배경 오탐 물체", "약 29~30%", "제외 — 배경으로 판단"],
        ]
    ),
    divider(),

    h2("🚌 승차대기 알림 워크플로우"),
    h3("LED 전광판 메시지 단계"),
    code("[교통약자 감지]\n      ↓\n① 점등: 교통약자 승차대기\n   버스 기사에게 즉시 알림\n      ↓\n② 유지: 사람이 있는 동안 계속 표시\n   3프레임 연속 감지 실패 시 해제\n      ↓\n③ 소등: 버스 출발 또는 탑승 완료\n   자동 리셋"),
    h3("감지 신뢰도 기준"),
    callout("한 번의 감지만으로는 알림을 보내지 않습니다. 연속된 감지를 통해 오탐을 줄입니다.", "⚠️"),
    make_table(
        ["상태", "조건", "동작"],
        [
            ["감지 시작", "교통약자 + 사람 동시 감지", "LED 점등, 서버 알림"],
            ["감지 유지", "계속 감지됨", "LED 유지"],
            ["감지 해제", "3프레임 연속 미감지", "LED 소등, 상태 초기화"],
        ]
    ),
    h3("센서 융합 (카메라 + 레이더)"),
    callout("카메라만 사용하면 야간·역광·안개 환경에 취약합니다. 레이더를 함께 사용하여 신뢰성을 높입니다.", "💡"),
    make_table(
        ["운용 모드", "설명"],
        [
            ["CAMERA 모드", "카메라만 사용"],
            ["RADAR 모드", "레이더만 사용"],
            ["FUSION 모드 (권장)", "카메라 + 레이더 동시 사용"],
        ]
    ),
    divider(),

    h2("🔧 하드웨어 구성 요소"),
    code("┌─────────────────────────────────┐\n│         버스 승강장              │\n│                                  │\n│  [카메라]  [레이더]              │\n│      ↘       ↙                  │\n│    [라즈베리파이]  <- 중앙 제어  │\n│         ↓                        │\n│    [LED 전광판]  <- 버스 기사용  │\n│         ↓                        │\n│    [냉각팬]     <- 온도 관리     │\n└─────────────────────────────────┘"),
    make_table(
        ["장치", "역할"],
        [
            ["IP 카메라", "실시간 영상 촬영 (RTSP 스트리밍)"],
            ["마이크로파 레이더", "사람 존재·움직임 감지 (야간·악천후 보조)"],
            ["라즈베리파이", "AI 처리 및 전체 시스템 제어"],
            ["LED 전광판 (M10)", "버스 기사용 교통약자 알림 표시"],
            ["냉각팬", "여름철 장치 과열 방지"],
        ]
    ),
    p("외부 연결: 승강장 라즈베리파이 -> (인터넷) -> 관리 서버 (175.45.215.53) -> 관리자 대시보드"),
    divider(),

    h2("⚙️ 주요 운영 모드"),
    make_table(
        ["모드 이름", "동작 방식", "적합 환경"],
        [
            ["SENSOR_MODE=camera", "카메라 AI만 사용", "야간 조명 충분, 맑은 날"],
            ["SENSOR_MODE=radar", "레이더만 사용", "카메라 고장 또는 개인정보 이슈"],
            ["SENSOR_MODE=both", "카메라 + 레이더", "일반 운용 (권장)"],
        ]
    ),
    make_table(
        ["융합 방식", "설명", "특성"],
        [
            ["FUSION_MODE=gating", "레이더가 먼저 감지해야 카메라 AI 실행", "전력 절약, 빠른 반응"],
            ["FUSION_MODE=confirm", "카메라 감지 후 레이더로 교차 검증", "높은 신뢰도, 오탐 감소"],
        ]
    ),
    divider(),

    h2("📡 시스템 상태 모니터링"),
    h3("실시간 데이터 전송 항목"),
    make_table(
        ["데이터", "설명"],
        [
            ["mobility_visible", "교통약자 현재 감지 여부 (true/false)"],
            ["count", "감지된 교통약자 수"],
            ["mobility_type", "종류 (Wheelchair / Crutch)"],
            ["confidence", "AI 감지 신뢰도 (0.0~1.0)"],
            ["led_on", "LED 전광판 현재 상태"],
            ["radar_presence", "레이더 감지 상태"],
        ]
    ),
    h3("알림 채널 (STOMP 토픽)"),
    make_table(
        ["토픽", "내용"],
        [
            ["/api/iot/mobility", "교통약자 감지 정보"],
            ["/api/iot/hid", "사람 존재 여부 (레이더 기반)"],
            ["/api/iot/overview", "전체 시스템 요약 상태"],
        ]
    ),
    divider(),

    h2("❓ 자주 묻는 질문"),
    h3("Q. 야간이나 비 오는 날도 작동하나요?"),
    callout("A. 네, 레이더 센서가 함께 작동하기 때문에 어두운 환경이나 악천후에도 감지가 가능합니다. 단, 카메라 단독 모드(SENSOR_MODE=camera)로 설정된 경우에는 조명이 필요합니다.", "✅"),
    h3("Q. 일반 자전거 타는 사람이 감지되지 않나요?"),
    callout("A. AI가 두 단계로 확인합니다.\n1. 사람이 있는지 확인\n2. 실제 휠체어·목발 기기가 보이는지 확인\n두 조건이 모두 만족될 때만 알림을 보냅니다. 단순히 자전거를 타거나 카트를 미는 사람은 감지되지 않습니다.", "✅"),
    h3("Q. 배경에 있는 물체가 오탐될 수 있나요?"),
    callout("A. 면적 필터를 적용하여 화면의 20% 이상을 차지하는 물체는 배경으로 판단해 무시합니다. 실제 사람이 탄 휠체어는 약 9~10% 정도 차지하므로 정상 감지됩니다.", "✅"),
    h3("Q. AI 모델은 얼마나 정확한가요?"),
    callout("A. 현재 운영 환경 기준\n- 휠체어 감지 신뢰도 임계값: 60% 이상\n- 오탐 방지를 위해 현장 데이터 수집 및 파인튜닝 진행 중\n- 수집 목표: 1,000장 (100장 x 10세트)", "✅"),
    divider(),

    h2("📌 핵심 흐름 한눈에 보기"),
    code("카메라 영상\n     ↓\nAI 모델 1: 사람 감지 (일반 AI)\nAI 모델 2: 교통약자 감지 (전용 AI)\n     ↓\n[두 모델 동시 감지 + 면적 필터 통과]\n     ↓\nLED 전광판 점등: 교통약자 승차대기\n+ 관리 서버 실시간 전송\n     ↓\n버스 기사 사전 인지 -> 안전한 탑승 지원\n\n레이더 보조: 야간·악천후 신뢰도 향상\n오탐 방지: 면적 필터 + 이중 모델 검증"),
    p("문의: 시스템 운영팀 | 최종 업데이트: 2026-05-06"),
]

def upload_batch(batch):
    data = {"children": batch}
    result = api("PATCH", f"/blocks/{PAGE_ID}/children", data)
    if result.get("object") == "error":
        print("ERROR:", result.get("message"))
        return False
    return True

batch_size = 20
total = len(blocks)
for i in range(0, total, batch_size):
    batch = blocks[i:i+batch_size]
    print(f"Uploading blocks {i+1}~{min(i+batch_size, total)} / {total}...")
    ok = upload_batch(batch)
    if not ok:
        break

print("Done!")
