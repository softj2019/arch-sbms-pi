import cv2
import numpy as np
import random
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

# 시뮬레이션 프레임 크기 및 측정 영역
frame_width = 640
frame_height = 480
roi_top_left = (100, 100)  # 측정 영역의 왼쪽 상단 좌표 (x, y)
roi_bottom_right = (500, 400)  # 측정 영역의 오른쪽 하단 좌표 (x, y)

# 사람 객체 클래스 정의
class SimulatedPerson:
    def __init__(self):
        # 사람의 초기 위치와 크기
        self.x = random.randint(0, frame_width - 30)
        self.y = random.randint(0, frame_height - 60)
        self.w = random.randint(20, 40)
        self.h = random.randint(40, 80)
        # 이동 속도
        self.dx = random.choice([-1, 1]) * random.randint(1, 3)
        self.dy = random.choice([-1, 1]) * random.randint(1, 3)

    def move(self):
        # 이동 및 경계 체크
        self.x += self.dx
        self.y += self.dy

        # 화면 경계를 벗어나지 않도록 반대 방향으로 속도 변경
        if self.x < 0 or self.x + self.w > frame_width:
            self.dx = -self.dx
        if self.y < 0 or self.y + self.h > frame_height:
            self.dy = -self.dy

    def get_position(self):
        return self.x, self.y, self.w, self.h

# 초기 사람 리스트 생성
num_people = 10  # 초기 사람 수
people = [SimulatedPerson() for _ in range(num_people)]

# 메인 루프
while True:
    # 빈 프레임 생성
    frame = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)

    # ROI 표시
    cv2.rectangle(frame, roi_top_left, roi_bottom_right, (255, 0, 0), 2)

    # ROI 안의 사람 수 계산
    current_in_roi = 0
    for person in people:
        person.move()
        x, y, w, h = person.get_position()

        # ROI 안에 있는 사람인지 확인
        is_in_roi = (roi_top_left[0] <= x <= roi_bottom_right[0] - w and
                     roi_top_left[1] <= y <= roi_bottom_right[1] - h)

        if is_in_roi:
            current_in_roi += 1

        # 사람 상자 그리기
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # ROI 안의 사람 수 표시
    cv2.putText(frame, f"In ROI: {current_in_roi}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    # 화면 출력
    cv2.imshow("People Counting in ROI", frame)

    # ESC 키로 종료
    if cv2.waitKey(50) & 0xFF == 27:
        break

# 리소스 해제
cv2.destroyAllWindows()
