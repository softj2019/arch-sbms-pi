#!/bin/bash
# mobility_aids 데이터셋을 zip으로 묶어 Google Drive 업로드 준비
cd /Users/my/app/sbms-pi
echo "압축 중..."
zip -r datasets/mobility_aids.zip datasets/mobility_aids/ \
  --exclude "*/.DS_Store"
echo "완료: datasets/mobility_aids.zip ($(du -sh datasets/mobility_aids.zip | cut -f1))"
echo ""
echo "Google Drive에 업로드하세요:"
echo "  1. drive.google.com 접속"
echo "  2. 내 드라이브 > 새 폴더 'sbms-pi' 생성"
echo "  3. mobility_aids.zip 드래그 업로드"
