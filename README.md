# 리뷰를 부탁해 — 법무 문서 (공개 호스팅)

「리뷰를 부탁해」 앱의 **개인정보처리방침**과 **이용약관**을 공개 URL로 제공하기 위한 정적 사이트입니다.
Google Play Console 제출 및 앱 내 링크에 사용합니다.

## 페이지
- 목록: `index.html`
- 개인정보처리방침: `privacy.html`
- 이용약관: `terms.html`

## 공개 URL (GitHub Pages)
- https://dawn840705.github.io/reviewsupporter-legal/
- https://dawn840705.github.io/reviewsupporter-legal/privacy.html
- https://dawn840705.github.io/reviewsupporter-legal/terms.html

## 정본(소스)
문서 정본은 메인(private) 레포의 `legal/*.md`입니다. 내용 변경 시 정본을 먼저 수정하고
본 레포의 HTML에 반영하세요.

## 어댑터 셀렉터 원격설정 (`selectors.json`)
법무 문서와 별개로, 앱의 **어댑터 셀렉터 원격설정 JSON**도 같은 Pages 인프라로 호스팅합니다.
- URL: https://dawn840705.github.io/reviewsupporter-legal/selectors.json
- 용도: 네이버 주문내역 DOM이 바뀌어 수집이 깨지면, **앱 빌드 없이** 이 파일의 셀렉터만 고쳐 전 사용자에 즉시 패치.
- 운영법: 메인 레포 `09_원격셀렉터_운영가이드.md`. 받는 건 셀렉터 문자열뿐(앱은 eval 안 함). 수정 시 `version`을 올릴 것.

시행일: 2026년 6월 3일 · 문의: dawn840705@gmail.com
