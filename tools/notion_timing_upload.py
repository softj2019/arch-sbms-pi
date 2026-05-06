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

def t(text, bold=False):
    r = {"type": "text", "text": {"content": text}}
    if bold:
        r["annotations"] = {"bold": True}
    return r

def h2(text):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t(text)]}}

def h3(text):
    return {"object": "block", "type": "heading_3", "heading_3": {"rich_text": [t(text)]}}

def p(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [t(text)]}}

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
    divider(),
    h2("⏱️ 상태별 메시지 지속 시간 및 해제 조건"),
    callout("아래 모든 수치는 실제 소스 코드(cv_ffmpeg.py / main_ctl.py)에서 측정한 값입니다. 환경변수로 조정 가능합니다.", "📌"),

    h3("1. AI 감지 주기"),
    make_table(
        ["항목", "값", "설명"],
        [
            ["AI 추론 주기", "5프레임마다 1회", "매 5프레임마다 휠체어·목발 AI 실행"],
            ["실제 시간 간격", "약 0.17초 (30fps 기준)", "5 프레임 ÷ 30fps = 0.167초"],
            ["환경변수", "MOBILITY_INFER_INTERVAL=5", "숫자 줄이면 더 빠른 감지, 숫자 늘리면 CPU 절약"],
        ]
    ),

    h3("2. 교통약자 감지 확정 → LED 점등"),
    make_table(
        ["단계", "소요 시간", "동작"],
        [
            ["휠체어 + 사람 동시 감지", "즉시 (첫 프레임)", "mobility_detected 신호 전송"],
            ["LED 전광판 점등", "즉시 (0초)", "교통약자 승차대기 메시지 표시"],
            ["서버 알림 전송", "즉시 (0초)", "관리 서버로 실시간 알림"],
        ]
    ),

    h3("3. LED 메시지 표시 지속 시간"),
    make_table(
        ["상태", "지속 시간", "조건"],
        [
            ["교통약자 감지 중 (기본)", "20초", "감지가 계속되면 메시지 유지"],
            ["교통약자 계속 감지 시", "자동 갱신 없음", "이미 표시 중이므로 20초 타이머 유지"],
            ["버튼으로 교통약자 갱신 시", "20초 재시작", "force_replace=True로 타이머 초기화"],
            ["버튼 활성 유지 시간", "20초 (BUTTON_HOLD_SEC)", "버튼 입력 후 count=0 수신되어도 20초간 유지"],
            ["수동 오버라이드 (관리자 설정)", "300초 (5분)", "관리자가 수동으로 LED 제어 시 5분 유지"],
        ]
    ),

    h3("4. 교통약자 사라짐 → LED 해제 조건"),
    callout("교통약자가 사라진다고 해서 즉시 LED가 꺼지지 않습니다. 오탐 방지를 위해 연속 미감지 횟수를 확인합니다.", "⚠️"),
    make_table(
        ["단계", "값", "설명"],
        [
            ["연속 미감지 판정 횟수", "3회 연속", "MOBILITY_CLEAR_STREAK=3"],
            ["1회 간격 (추론 주기)", "약 0.17초", "5프레임 × (1/30초)"],
            ["해제까지 총 소요 시간", "약 0.5초", "3회 × 0.17초 = 0.5초 연속 미감지 후 해제"],
            ["해제 환경변수", "MOBILITY_CLEAR_STREAK=3", "숫자 늘리면 더 느리게 해제 (오탐 방지 강화)"],
        ]
    ),

    h3("5. 해제 후 전광판 전환 시나리오"),
    code("교통약자 사라짐 감지 (3회 연속 미감지)\n      ↓\n  사람(일반인)이 아직 있나?\n  ├── YES → 승차대기 메시지 유지 (사람 대기 중)\n  └── NO  → 시계 화면으로 전환 (대기자 없음)"),
    make_table(
        ["시나리오", "전광판 전환 내용", "이유"],
        [
            ["교통약자 사라짐 + 사람 있음", "승차대기 메시지 유지", "일반 승객이 아직 대기 중"],
            ["교통약자 사라짐 + 사람 없음", "시계 화면으로 전환", "승강장에 아무도 없음"],
            ["count=0 수신 + 버튼 유효 기간 중", "LED 유지 (전환 대기)", "버튼 20초 타이머 만료까지 대기"],
            ["count=0 수신 + 버튼 기간 만료", "시계 화면으로 전환", "정상 종료"],
        ]
    ),

    h3("6. LED 전광판 운영 시간"),
    make_table(
        ["설정 항목", "기본값", "설명"],
        [
            ["점등 시작 시간", "17:00 (오후 5시)", "ledLiteOnTime — 서버에서 설정 가능"],
            ["소등 시간", "04:00 (새벽 4시)", "ledLiteOffTime — 서버에서 설정 가능"],
            ["운영 시간", "오후 5시 ~ 새벽 4시 (11시간)", "심야·새벽에도 운영"],
            ["설정 갱신 주기", "30초마다 서버에서 최신값 수신", "실시간 원격 설정 변경 가능"],
        ]
    ),

    h3("7. 전체 타이밍 흐름 요약"),
    code("[휠체어 + 사람 감지]\n       ↓ 즉시\n[LED 점등: 교통약자 승차대기]\n       ↓ 20초 유지\n[교통약자 이동 / 탑승]\n       ↓ AI가 3회(약 0.5초) 연속 미감지 확인\n[mobility_cleared 신호 발생]\n       ↓\n  사람 있음? YES → 승차대기 메시지 유지\n  사람 있음? NO  → 시계 화면 전환\n       ↓\n[다음 교통약자 대기 상태로 초기화]"),

    callout("핵심 요약\n- 감지 즉시 LED 점등 (지연 없음)\n- LED 메시지 유지: 20초 (마지막 감지 기준)\n- 해제 판정: 약 0.5초 연속 미감지\n- 해제 후: 사람 있으면 승차대기 유지 / 없으면 시계 전환\n- LED 운영 시간: 17:00 ~ 04:00 (서버에서 조정 가능)", "⏱️"),
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
